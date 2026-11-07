# 微信插件市场

[鲸鱼娘 · 微信控制台](https://github.com/linxisama/wechatwhalegirl) 的第三方插件仓库，共 **19 个**。
每个包都是「单文件插件包」形态：一个 zip，解压只有 `plugin.json`、`<id>.py`、`使用说明.md` 三个文件，不含依赖、不需要编译。

## 怎么装

前提：已经装好并跑起来那个控制台（本仓库只是插件包，不是控制台）。

1. 下载本仓库（`git clone` 或右上角 Download ZIP 都行）；
2. 打开控制台 ->「插件」页 ->「添加插件」；
3. 在「本地文件」里选中 `packages/` 下的某个 zip；
4. 先点「检查」，看清名称、说明与安全检查结果；
5. 点「确认安装」（同名插件升级时勾选「覆盖」）；
6. 回到插件页手动启用，并按需调参数。

装完的插件落在控制台数据目录的 `custom_plugins/` 下，并登记进 `custom_plugins.json`；卸载直接在插件页删，不用回来找本仓库。

## 仓库结构

```
index.json         机器可读索引（id / 版本 / 分类 / 文件名 / sha256 / 字节数）
packages/          19 个可直接安装的 zip
使用说明/          每个插件一页，不解压也能看
tools/             重建与校验脚本（普通用户用不到，见文末）
LICENSE            MIT（只覆盖本仓库的整理工作，不覆盖插件代码，详见文件内）
```

## 收录插件

| # | 插件 | id | 版本 | 分类 | 包文件 | 字节 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 群友好感度 | `affinity` | 1 | 社交 | `群友好感度-affinity.zip` | 10346 |
| 2 | 人设存档隔离 | `archive_isolation` | 1 | 实用 | `人设存档隔离-archive_isolation.zip` | 2353 |
| 3 | B站运营看板 | `bilibili_account` | 1.1.0 | 实用 | `B站运营看板-bilibili_account.zip` | 4218 |
| 4 | 缓存稳定性 | `cache_stability` | 1 | 实用 | `缓存稳定性-cache_stability.zip` | 4706 |
| 5 | 跨会话认人 | `cross_chat_link` | 1 | 社交 | `跨会话认人-cross_chat_link.zip` | 2628 |
| 6 | 提前收尾（省 token） | `early_finish` | 1 | 实用 | `提前收尾（省 token）-early_finish.zip` | 5895 |
| 7 | 跟着贴表情 | `emoji_echo` | 1 | 社交 | `跟着贴表情-emoji_echo.zip` | 3371 |
| 8 | 群友花费统计 | `group_cost_report` | 1 | 实用 | `群友花费统计-group_cost_report.zip` | 7223 |
| 9 | 长图分段阅读 | `long_image_reader` | 1 | 媒体 | `长图分段阅读-long_image_reader.zip` | 3607 |
| 10 | 市场探针 | `market_probe` | 1 | 实用 | `市场探针-market_probe.zip` | 7744 |
| 11 | 消息表情回应 | `msg_reaction` | 1 | 社交 | `消息表情回应-msg_reaction.zip` | 4504 |
| 12 | 主人识别 | `owner_identity` | 1.0.0 | 消息 | `主人识别-owner_identity.zip` | 2559 |
| 13 | 回复时机与引用 | `reply_freshness` | 1 | 社交 | `回复时机与引用-reply_freshness.zip` | 7028 |
| 14 | 语音转文字（QQ 原生） | `speech_to_text_qq` | 1 | 媒体 | `语音转文字（QQ 原生）-speech_to_text_qq.zip` | 5143 |
| 15 | 表情包库上限 | `sticker_cap` | 1 | 媒体 | `表情包库上限-sticker_cap.zip` | 6074 |
| 16 | 正在输入提示 | `typing_indicator` | 1 | 实用 | `正在输入提示-typing_indicator.zip` | 5342 |
| 17 | 语音控制台 | `voice_console` | 2.6.0 | 语音 | `语音控制台-voice_console.zip` | 6093 |
| 18 | 语音回复 | `voice_reply` | 1.0.0 | 语音 | `语音回复-voice_reply.zip` | 2907 |
| 19 | 鲸鱼签名 | `whale_signature` | 1.0.0 | 消息 | `鲸鱼签名-whale_signature.zip` | 3242 |

逐个的功能与配置项见 `使用说明/<id>.md`；校验和见 `index.json`。

## 没收录的包（实测装不进去）

| 插件 | id | 原因 |
| --- | --- | --- |
| 热梗与热点收集 | `hot_trend_tracker` | 缺少依赖模块 src.public_web（控制台没有这个模块，导入即 ModuleNotFoundError） |
| 搜索词清理与联网查找 | `search_query_hygiene` | 缺少依赖模块 src.public_web（同上） |
| 表情包制作（NoneBot 适配） | `memes` | 缺少依赖模块 src.meme_service（NoneBot 服务层不存在） |
| 智能斗图接龙 | `sticker_battle` | 导入失败：cannot import name 'source_key' from 'src.sticker_library' |
| QQ Agent 能力桥 | `qqagent_bridge` | 安全检查未通过：含被禁止的用法「启动子进程 subprocess」 |

这 5 个包在源池里存在，但控制台装不上，放进来只会让人装到一半失败，因此不收。

## 风险提示

- **插件就是会被 import 执行的代码。** 安装前请自己看一眼「检查」结果与 `使用说明/`，本仓库只做格式统一与可安装性验证，不代表对插件行为做过审计。
- 安装器会拦截 `os.system` / `os.popen` / `subprocess` / `eval` / `exec` / `__import__` / `shutil.rmtree` / `socket` / `ctypes` / `pickle` / `winreg` 等危险用法；本仓库的包已通过这道检查，但通过检查不等于没有副作用。
- 主动发言、外发类能力默认关闭，必须由你在插件页显式启用；任何插件都不能绕过控制台的发送闸门、间隔与超时规则。
- **与内置插件同 id 的包会被内置模块遮蔽**（`list_plugins` 里 source 恒为 `builtin`），所以内置的 33 个 id 一律不进本市场。
- 控制台的「插件包文件夹」通道不可用（实测 `affinity load failed (RuntimeError)`，`pack_status installed=0 broken=1`），只能用这里的单文件 zip 通道。

## 重建与校验（仓库维护者用）

重建要读源包池、并 import 控制台源码里的插件清单与插件管理器，这两样不在本仓库里，必须显式指定：

```bash
export WECHAT_MARKET_SOURCE=<源包池目录>      # 一批 whale-plugin zip
export WECHAT_CONSOLE_ROOT=<控制台源码根>     # 含 src/plugins/manager.py

python tools/build_market.py    # 重建 packages/ index.json 使用说明/ README.md
python tools/verify_market.py   # 逐个真实安装进临时目录，任一失败退出码非 0
```

两个脚本都只读源包池，不写控制台；校验用 `tempfile` 建独立临时数据目录，装完即删，不会碰到你正在用的控制台。

构建是幂等的：zip 内时间戳取自源包集合里最新的 mtime，所以重复构建逐字节一致、sha256 不变。本文件由 `build_market.py` 生成，手改会在下次重建时被覆盖。索引生成时间：2026-10-24T12:52:04Z。
