"""微信插件市场校验器：用控制台真实安装器把每个包逐个装进临时目录，
并确认能被 PluginManager 以 source=custom 注册。

判据与控制台真实链路一致（src/wechat_app.py:3080 的 _finish_install）：
inspect_local -> install_from_file -> register_custom -> reload -> 必须在 _plugins 里。

用法：
    python tools/verify_market.py --console <控制台源码根>
    WECHAT_CONSOLE_ROOT=<控制台源码根> python tools/verify_market.py

退出码：全部 PASS 为 0，任一 FAIL 为 1。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # 导入 build_market 时别在仓库里留 __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_market import (  # noqa: E402
    DEFAULT_OUT, ENV_CONSOLE, install_and_register, make_manager,
)


def load_index(market_dir: Path) -> dict:
    path = market_dir / "index.json"
    if not path.is_file():
        raise SystemExit("找不到 index.json：先跑 python tools/build_market.py")
    return json.loads(path.read_text("utf-8"))


def verify_one(console_root: Path, zip_path: Path, plugin_id: str) -> str:
    """独立临时目录装一个插件；返回空串表示通过，否则返回失败原因。"""
    temp = Path(tempfile.mkdtemp(prefix="verify-market-"))
    try:
        manager = make_manager(console_root, temp / "data")
        return install_and_register(manager, zip_path, plugin_id)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="校验微信插件市场里的每个包能否真的装进控制台")
    parser.add_argument("--market", default=str(DEFAULT_OUT), help="市场目录，默认本仓库根")
    parser.add_argument("--console", default=os.environ.get(ENV_CONSOLE, ""),
                        help="控制台源码目录（也可用环境变量 %s）" % ENV_CONSOLE)
    args = parser.parse_args(argv)
    if not args.console:
        parser.error("必须指定 --console（或设置 %s）：校验要在真实控制台里 import "
                     "插件管理器，没有源码跑不了。" % ENV_CONSOLE)

    market_dir = Path(args.market)
    console_root = Path(args.console)
    if not (console_root / "src" / "plugins" / "manager.py").is_file():
        raise SystemExit("控制台目录不对，找不到 src/plugins/manager.py：%s" % console_root)

    index = load_index(market_dir)
    plugins = index.get("plugins") or []
    if not plugins:
        raise SystemExit("index.json 里没有插件条目")

    print("市场目录：%s" % market_dir)
    print("控制台：  %s" % console_root)
    print("共 %d 个插件待校验" % len(plugins))
    print("-" * 60)

    failures = []
    for entry in plugins:
        plugin_id = entry.get("id") or "?"
        zip_path = market_dir / "packages" / str(entry.get("file") or "")
        if not zip_path.is_file():
            reason = "包文件不存在：%s" % zip_path.name
        else:
            try:
                reason = verify_one(console_root, zip_path, plugin_id)
            except Exception as exc:  # 校验器自身不能被单个坏包拖崩
                reason = "校验异常：%s: %s" % (type(exc).__name__, exc)
        if reason:
            failures.append((plugin_id, reason))
            print("FAIL  %-22s %s" % (plugin_id, reason))
        else:
            print("PASS  %-22s v%s" % (plugin_id, entry.get("version")))

    print("-" * 60)
    passed = len(plugins) - len(failures)
    print("结果：%d/%d 通过" % (passed, len(plugins)))
    if failures:
        print("失败清单：")
        for plugin_id, reason in failures:
            print("  - %s: %s" % (plugin_id, reason))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
