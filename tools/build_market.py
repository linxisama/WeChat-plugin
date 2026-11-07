"""build_market.py — 把可用的第三方微信插件重建成统一的市场仓库。

产物（全部在仓库根目录下，重复运行逐字节一致）：
    packages/<中文名>-<id>.zip   每个包内恰好 3 个文件：plugin.json + <id>.py + 使用说明.md
    index.json                   机器可读索引（含 sha256 / bytes）
    使用说明/<id>.md              单页说明，不用解压也能看
    README.md                    人类可读索引（收录表 + 未收录表 + 风险提示）

为什么每个插件单独成包：控制台「插件中心 -> 添加插件 -> 本地文件」一次只装一个 zip，
单包也让安装器的预检与回滚按包生效。

为什么 zip 内时间戳写死：zip 头里的 date_time 会进字节流，用「现在」就等于每次 build
都换一份 sha256，幂等验收必挂。这里统一取源包集合里最新的 mtime，既稳定又不撒谎。

重建需要两样本仓库里没有的东西，必须显式指定：
    --source    源包池目录（一批 whale-plugin zip，同 id 自动取最高版本）
    --console   控制台源码根目录（要 import src.plugin_manifest 与 src.plugins.manager）

用法：
    python tools/build_market.py --source <源包池> --console <控制台源码根>
    WECHAT_MARKET_SOURCE=... WECHAT_CONSOLE_ROOT=... python tools/build_market.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True   # 不往控制台目录写 __pycache__
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

# 产物固定落在本脚本的上一级目录（仓库根），与仓库位置无关。
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT

# 源包池与控制台源码只在作者本机存在，仓库里不带；缺省从环境变量取，再缺就报错。
ENV_SOURCE = "WECHAT_MARKET_SOURCE"
ENV_CONSOLE = "WECHAT_CONSOLE_ROOT"

SCHEMA_VERSION = 1
MARKET_FORMAT = "whale-wechat-plugin"
USAGE_NAME = "使用说明.md"

# 收录名单：19 个唯一 id，逐个实测可安装且可被控制台加载（不累积、不重置）
TARGET_IDS = (
    "affinity", "archive_isolation", "bilibili_account", "cache_stability",
    "cross_chat_link", "early_finish", "emoji_echo", "group_cost_report",
    "long_image_reader", "market_probe", "msg_reaction", "owner_identity",
    "reply_freshness", "speech_to_text_qq", "sticker_cap", "typing_indicator",
    "voice_console", "voice_reply", "whale_signature",
)

# 实测装不进去的包：不收录，但必须在 README 里写清原因（不含糊、不隐藏）
EXCLUDED = (
    ("hot_trend_tracker", "热梗与热点收集",
     "缺少依赖模块 src.public_web（控制台没有这个模块，导入即 ModuleNotFoundError）"),
    ("search_query_hygiene", "搜索词清理与联网查找",
     "缺少依赖模块 src.public_web（同上）"),
    ("memes", "表情包制作（NoneBot 适配）",
     "缺少依赖模块 src.meme_service（NoneBot 服务层不存在）"),
    ("sticker_battle", "智能斗图接龙",
     "导入失败：cannot import name 'source_key' from 'src.sticker_library'"),
    ("qqagent_bridge", "QQ Agent 能力桥",
     "安全检查未通过：含被禁止的用法「启动子进程 subprocess」"),
)

CATEGORY_ZH = {
    "social": "社交", "utility": "实用", "media": "媒体", "voice": "语音",
    "message": "消息", "personality": "人格", "knowledge": "知识", "rhythm": "节奏",
}

SAFE_NAME = str.maketrans({"/": "_", "\\": "_", ":": "_", "*": "_", "?": "_",
                           '"': "_", "<": "_", ">": "_", "|": "_"})


# ── 小工具 ────────────────────────────────────────────────────────────────────
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version_key(text: str):
    """把 "1.1.0" / "1" / "2.6.0" 归一成可比较的整数元组（缺位补 0）。"""
    parts = [int(p) for p in re.findall(r"\\d+", str(text or ""))] or [0]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _category_zh(category: str) -> str:
    return CATEGORY_ZH.get(category, category or "未分类")


def _one_line(text: str) -> str:
    return " ".join(str(text or "").split())


# ── 读源包 ────────────────────────────────────────────────────────────────────
def _read_source(path: Path) -> dict:
    """读一个源 zip：返回归一化清单、原始 JSON、源码文本与所取成员名。"""
    from src.plugin_manifest import load_manifest, validate_manifest

    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if not n.endswith("/")]
        manifest_member = None
        for name in sorted(names, key=lambda n: (len(n.split("/")), n)):
            if name.split("/")[-1].lower() == "plugin.json":
                manifest_member = name
                break
        if manifest_member is None:
            raise ValueError("压缩包里没有 plugin.json")
        raw = json.loads(archive.read(manifest_member).decode("utf-8-sig"))
        manifest = load_manifest(raw)
        problems = validate_manifest(manifest)
        if problems:
            raise ValueError("清单校验未通过：" + "；".join(problems))
        code_member = None
        entry = str(manifest.get("entry") or "")
        if entry:
            wanted = entry.partition(":")[0].strip()
            for name in names:
                if name == wanted or name.endswith("/" + wanted):
                    code_member = name
                    break
        if code_member is None:
            for name in names:
                if name.split("/")[-1] == str(manifest["id"]) + ".py":
                    code_member = name
                    break
        if code_member is None:
            pys = [n for n in names if n.endswith(".py")]
            if not pys:
                raise ValueError("压缩包里没有 .py 文件")
            code_member = pys[0]
        code = archive.read(code_member).decode("utf-8")
    return {"manifest": manifest, "raw": raw, "code": code,
            "code_member": code_member, "source_file": path.name}


def _collect_sources(source_dir: Path) -> dict:
    """按 plugin.json 里的 id 归集源包（不按文件名猜），同 id 取版本最高的那个。"""
    chosen: dict = {}
    for path in sorted(source_dir.glob("*.zip")):
        try:
            item = _read_source(path)
        except Exception as exc:                     # 坏包不影响其它包
            print("  跳过 %s：%s" % (path.name, exc))
            continue
        plugin_id = str(item["manifest"].get("id") or "")
        if plugin_id not in TARGET_IDS:
            continue
        previous = chosen.get(plugin_id)
        newer = (previous is None or
                 _version_key(item["manifest"]["version"]) >
                 _version_key(previous["manifest"]["version"]))
        if newer:
            chosen[plugin_id] = item
    return chosen


# ── 生成说明文本 ──────────────────────────────────────────────────────────────
def _config_rows(raw: dict) -> list:
    """源清单里的 config 数组（whale-plugin 方言才有）；没有就返回空。"""
    rows = raw.get("config")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and row.get("key")]


def _usage_text(item: dict) -> str:
    manifest = item["manifest"]
    plugin_id = manifest["id"]
    lines = [
        "# " + manifest["name"],
        "",
        "- 插件 id：`" + plugin_id + "`",
        "- 版本：`" + str(manifest["version"]) + "`",
        "- 分类：" + _category_zh(str(item["raw"].get("category") or "")),
        "- 源包：`" + item["source_file"] + "`（打包时取其 `" + item["code_member"] + "`）",
        "",
        "## 功能",
        "",
        manifest["description"] or "（源清单没有写说明）",
        "",
        "## 安装",
        "",
        "1. 打开控制台 ->「插件中心」；",
        "2. 点「添加插件」->「本地文件」，选择本压缩包；",
        "3. 先点「检查」，确认名称、说明与安全检查通过；",
        "4. 确认无误后安装（更新时勾选「覆盖同名插件」）。",
        "",
        "装完不会自动生效：到插件页手动启用并按需调参数。不需要时在插件中心删除。",
        "",
    ]
    rows = _config_rows(item["raw"])
    if rows:
        lines += ["## 配置项", "",
                  "| 键 | 名称 | 类型 | 默认值 | 说明 |",
                  "| --- | --- | --- | --- | --- |"]
        for row in rows:
            default = row.get("default")
            default = "（无）" if default is None else "`" + str(default) + "`"
            lines.append("| `" + str(row["key"]) + "` | "
                         + (_one_line(row.get("label")) or str(row["key"])) + " | "
                         + str(row.get("type", "")) + " | " + default + " | "
                         + _one_line(row.get("description")) + " |")
        lines.append("")
    lines += [
        "## 风险与边界",
        "",
        "- 插件是会被 import 执行的代码，装之前请先看「检查」结果与上面的配置项。",
        "- 安装器会拦截 os.system / subprocess / eval / exec / socket / ctypes / "
        "pickle / winreg 等用法；本包已通过该检查。",
        "- 主动发言、外发类能力默认关闭，必须由你在插件页显式启用才会生效。",
        "- 本页说明取自源包清单，未对插件行为做额外审计；第三方插件的行为自负。",
        "",
    ]
    return "\n".join(lines)


# ── 打包 ──────────────────────────────────────────────────────────────────────
def _market_manifest(item: dict) -> dict:
    manifest = item["manifest"]
    return {
        "format": MARKET_FORMAT,
        "format_version": 1,
        "id": manifest["id"],
        "name": manifest["name"],
        "version": manifest["version"],
        "api_version": manifest["api_version"],
        "entry": str(manifest["id"]) + ".py",
        "category": str(item["raw"].get("category") or ""),
        "description": manifest["description"],
        "market": True,
    }


def _write_zip(target: Path, members: list, stamp: tuple) -> None:
    """写一个内容与时间戳都确定的 zip；members 是 [(名字, 文本)]，顺序即包内顺序。"""
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in members:
            info = zipfile.ZipInfo(name, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3          # 固定为 Unix，避免跨平台头差异
            info.external_attr = 0o644 << 16
            archive.writestr(info, text.encode("utf-8"))


# ── 真实验证（build 与 verify 共用同一条链路） ────────────────────────────────
def make_manager(console_root: Path, data_dir: Path):
    """建一个指向临时数据目录的 PluginManager（绝不碰控制台真实 data/）。"""
    if str(console_root) not in sys.path:
        sys.path.insert(0, str(console_root))
    from src.plugins.manager import PluginManager
    return PluginManager(data_dir, custom_plugins_dir=data_dir / "custom_plugins")


def install_and_register(manager, zip_path: Path, plugin_id: str) -> str:
    """复刻控制台真实链路（wechat_app.py:3080 的 _finish_install）：
    inspect_local -> install_from_file -> register_custom -> reload -> 必须在 _plugins 里。
    返回空串表示成功，否则返回失败原因。
    """
    from src import plugin_installer

    info = plugin_installer.inspect_local(zip_path)
    if not info["ok"]:
        return "预检未通过：" + "；".join(info["problems"])
    result = plugin_installer.install_from_file(
        zip_path, manager.custom_plugins_dir, confirmed=True, overwrite=True)
    if result["plugin_id"] != plugin_id:
        return "装成了 %s，与清单 id %s 不一致" % (result["plugin_id"], plugin_id)
    manager.register_custom(result["plugin_id"])
    manager.reload()
    if plugin_id not in manager._plugins:
        return "已写入但加载失败（PluginManager 未注册该插件）"
    source = manager.plugin_source(plugin_id)
    if source != "custom":
        return "加载来源是 %s，不是 custom（可能被内置同 id 遮蔽）" % source
    return ""


# ── README ────────────────────────────────────────────────────────────────────
def _readme(entries: list, generated_at: str) -> str:
    total = len(entries)
    lines = [
        "# 微信插件市场",
        "",
        "[鲸鱼娘 · 微信控制台](https://github.com/linxisama/wechatwhalegirl) 的第三方插件仓库，"
        "共 **%d 个**。" % total,
        "每个包都是「单文件插件包」形态：一个 zip，解压只有 "
        "`plugin.json`、`<id>.py`、`使用说明.md` 三个文件，不含依赖、不需要编译。",
        "",
        "## 怎么装",
        "",
        "前提：已经装好并跑起来那个控制台（本仓库只是插件包，不是控制台）。",
        "",
        "1. 下载本仓库（`git clone` 或右上角 Download ZIP 都行）；",
        "2. 打开控制台 ->「插件」页 ->「添加插件」；",
        "3. 在「本地文件」里选中 `packages/` 下的某个 zip；",
        "4. 先点「检查」，看清名称、说明与安全检查结果；",
        "5. 点「确认安装」（同名插件升级时勾选「覆盖」）；",
        "6. 回到插件页手动启用，并按需调参数。",
        "",
        "装完的插件落在控制台数据目录的 `custom_plugins/` 下，"
        "并登记进 `custom_plugins.json`；卸载直接在插件页删，不用回来找本仓库。",
        "",
        "## 仓库结构",
        "",
        "```",
        "index.json         机器可读索引（id / 版本 / 分类 / 文件名 / sha256 / 字节数）",
        "packages/          %d 个可直接安装的 zip" % total,
        "使用说明/          每个插件一页，不解压也能看",
        "tools/             重建与校验脚本（普通用户用不到，见文末）",
        "LICENSE            MIT（只覆盖本仓库的整理工作，不覆盖插件代码，详见文件内）",
        "```",
        "",
        "## 收录插件",
        "",
        "| # | 插件 | id | 版本 | 分类 | 包文件 | 字节 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, entry in enumerate(entries, 1):
        lines.append("| %d | %s | `%s` | %s | %s | `%s` | %d |" % (
            index, entry["name"], entry["id"], entry["version"],
            _category_zh(entry["category"]), entry["file"], entry["bytes"]))
    lines += [
        "",
        "逐个的功能与配置项见 `使用说明/<id>.md`；校验和见 `index.json`。",
        "",
        "## 没收录的包（实测装不进去）",
        "",
        "| 插件 | id | 原因 |",
        "| --- | --- | --- |",
    ]
    for plugin_id, name, reason in EXCLUDED:
        lines.append("| %s | `%s` | %s |" % (name, plugin_id, reason))
    lines += [
        "",
        "这 %d 个包在源池里存在，但控制台装不上，"
        "放进来只会让人装到一半失败，因此不收。" % len(EXCLUDED),
        "",
        "## 风险提示",
        "",
        "- **插件就是会被 import 执行的代码。** 安装前请自己看一眼「检查」结果与"
        " `使用说明/`，本仓库只做格式统一与可安装性验证，"
        "不代表对插件行为做过审计。",
        "- 安装器会拦截 `os.system` / `os.popen` / `subprocess` / `eval` / "
        "`exec` / `__import__` / `shutil.rmtree` / `socket` / `ctypes` / "
        "`pickle` / `winreg` 等危险用法；本仓库的包已通过这道检查，"
        "但通过检查不等于没有副作用。",
        "- 主动发言、外发类能力默认关闭，必须由你在插件页显式启用；"
        "任何插件都不能绕过控制台的发送闸门、间隔与超时规则。",
        "- **与内置插件同 id 的包会被内置模块遮蔽**"
        "（`list_plugins` 里 source 恒为 `builtin`），"
        "所以内置的 33 个 id 一律不进本市场。",
        "- 控制台的「插件包文件夹」通道不可用"
        "（实测 `affinity load failed (RuntimeError)`，"
        "`pack_status installed=0 broken=1`），只能用这里的单文件 zip 通道。",
        "",
        "## 重建与校验（仓库维护者用）",
        "",
        "重建要读源包池、并 import 控制台源码里的插件清单与插件管理器，"
        "这两样不在本仓库里，必须显式指定：",
        "",
        "```bash",
        "export WECHAT_MARKET_SOURCE=<源包池目录>      # 一批 whale-plugin zip",
        "export WECHAT_CONSOLE_ROOT=<控制台源码根>     # 含 src/plugins/manager.py",
        "",
        "python tools/build_market.py    # 重建 packages/ index.json 使用说明/ README.md",
        "python tools/verify_market.py   # 逐个真实安装进临时目录，任一失败退出码非 0",
        "```",
        "",
        "两个脚本都只读源包池，不写控制台；校验用 `tempfile` 建独立临时数据目录，"
        "装完即删，不会碰到你正在用的控制台。",
        "",
        "构建是幂等的：zip 内时间戳取自源包集合里最新的 mtime，"
        "所以重复构建逐字节一致、sha256 不变。本文件由 `build_market.py` 生成，"
        "手改会在下次重建时被覆盖。索引生成时间：%s。" % generated_at,
        "",
    ]
    return "\n".join(lines)


# ── 主流程 ────────────────────────────────────────────────────────────────────
def build(source_dir: Path, out_dir: Path, console_root: Path) -> int:
    if not source_dir.is_dir():
        print("✗ 源包池不存在：%s" % source_dir)
        return 1
    if not (console_root / "src" / "plugins" / "manager.py").is_file():
        print("✗ 控制台源码根不对（找不到 src/plugins/manager.py）：%s" % console_root)
        return 1
    print("源目录：%s" % source_dir)
    print("输出目录：%s" % out_dir)
    # 读源包就要用控制台的 plugin_manifest 做校验，所以先挂上源码根（只读 import）。
    if str(console_root) not in sys.path:
        sys.path.insert(0, str(console_root))
    sources = _collect_sources(source_dir)
    missing = [pid for pid in TARGET_IDS if pid not in sources]
    if missing:
        print("✗ 源目录里找不到这些 id 的包：%s" % missing)
        return 1

    stamp_epoch = max((source_dir / item["source_file"]).stat().st_mtime
                      for item in sources.values())
    stamp = tuple(time.localtime(stamp_epoch)[:6])
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stamp_epoch))

    packages_dir = out_dir / "packages"
    usage_dir = out_dir / "使用说明"
    for directory in (packages_dir, usage_dir):
        directory.mkdir(parents=True, exist_ok=True)
    for stale in packages_dir.glob("*.zip"):      # 幂等：先清掉上一轮的产物
        stale.unlink()
    for stale in usage_dir.glob("*.md"):
        stale.unlink()

    work = Path(tempfile.mkdtemp(prefix="market_build_"))
    entries = []
    try:
        manager = make_manager(console_root, work / "data")
        for plugin_id in TARGET_IDS:
            item = sources[plugin_id]
            manifest = item["manifest"]
            usage = _usage_text(item)
            safe_name = manifest["name"].translate(SAFE_NAME).strip() or plugin_id
            archive = packages_dir / ("%s-%s.zip" % (safe_name, plugin_id))
            _write_zip(archive, [
                ("plugin.json", json.dumps(_market_manifest(item),
                                           ensure_ascii=False, indent=2) + "\n"),
                (plugin_id + ".py", item["code"]),
                (USAGE_NAME, usage),
            ], stamp)

            reason = install_and_register(manager, archive, plugin_id)
            if reason:
                print("✗ %s 未通过真实安装验证：%s" % (plugin_id, reason))
                return 1

            (usage_dir / (plugin_id + ".md")).write_text(usage, encoding="utf-8")
            entries.append({
                "id": plugin_id,
                "name": manifest["name"],
                "version": manifest["version"],
                "description": manifest["description"],
                "file": archive.name,
                "sha256": _sha256(archive),
                "bytes": archive.stat().st_size,
                "category": str(item["raw"].get("category") or ""),
                "verified": True,
            })
            print("✓ %s %s -> %s" % (plugin_id, manifest["version"], archive.name))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    index = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "total": len(entries),
        "plugins": entries,
    }
    (out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "README.md").write_text(
        _readme(entries, generated_at), encoding="utf-8")

    print("")
    print("完成：%d 个插件，共 %d 字节"
          % (len(entries), sum(entry["bytes"] for entry in entries)))
    print("index.json：%s" % (out_dir / "index.json"))
    return 0 if len(entries) == len(TARGET_IDS) else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="重建微信插件市场仓库")
    parser.add_argument("--source", default=os.environ.get(ENV_SOURCE, ""),
                        help="只读源包池目录（也可用环境变量 %s）" % ENV_SOURCE)
    parser.add_argument("--console", default=os.environ.get(ENV_CONSOLE, ""),
                        help="控制台源码根目录（也可用环境变量 %s）" % ENV_CONSOLE)
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录，默认本仓库根")
    args = parser.parse_args(argv)
    if not args.source or not args.console:
        parser.error("必须指定 --source 与 --console（或设置 %s / %s）："
                     "重建要读源包池，并 import 控制台的插件清单与插件管理器。"
                     % (ENV_SOURCE, ENV_CONSOLE))
    return build(Path(args.source), Path(args.out), Path(args.console))


if __name__ == "__main__":
    raise SystemExit(main())
