# Wild Rift Skin Version

[English](README.md)

一个按国际服发布补丁浏览《英雄联盟手游》皮肤的静态档案。

[League Skin Version](https://github.com/syy674998887/league-skin-version) 的手游镜像站，沿用相同的核心浏览界面，使用独立的手游数据更新流程。

[打开网站](https://syy674998887.github.io/wild-rift-skin-version/) · [GitHub 仓库](https://github.com/syy674998887/wild-rift-skin-version)

本项目是非官方、免费、非商业社区项目，未获得 Riot Games 认可或赞助。

## 功能

- 按版本浏览皮肤，单列 UPCOMING、版本待确定和地区待确定分组；地区分组置顶并默认折叠。
- 皮肤详情显示该款皮肤的上线日期；PATCH 标题只显示补丁上线日期。日期缺失时不显示，已知的未来上线日期标为“预计上线”。
- 搜索中英文名称，按英雄、系列、国服等级、Legacy、炫彩及版本依据筛选。
- 按素材情况切换原始、Wiki 原画和加载界面图片；窗口按实际图片宽高调整，并提供同英雄、同系列关联列表。
- 通过“视频”按钮直接打开自动匹配的 SkinSpotlights 视频。
- 支持响应式筛选布局、深浅主题、键盘导航及减少动态效果设置；搜索和筛选状态可通过网址分享。
- 等级／Legacy 图标加载失败时回退为文字。炫彩图失败时保留浏览器破图标记和替代文字，名称与色块继续显示。

Standard／“标准”等级不在卡片或详情中显示，数据和筛选仍保留。详情中的 UPCOMING 使用普通文字，推断及待确定状态使用简短标签。编号和详细依据保存在数据中；编号不在详情展示，也不参与搜索。

## 数据来源

皮肤更新流程使用三组核心来源：

| 来源 | 用途 |
| --- | --- |
| [League Wiki 手游模块](https://wiki.leagueoflegends.com/en-us/Module:SkinDataWR/data)、WR 版本页与手游文件 | 皮肤身份与目录、上线日期、版本记录、系列、Legacy、炫彩和图片 |
| 国服官方[英雄目录](https://game.gtimg.cn/images/lgamem/act/lrlib/js/heroList/hero_list.js)与[皮肤目录](https://game.gtimg.cn/images/lgamem/act/lrlib/js/skins/skins.js) | 中文名称、明确标注的国服等级及补充图片 |
| 国际服[英雄页面](https://wildrift.leagueoflegends.com/en-us/champions/)与[补丁公告](https://wildrift.leagueoflegends.com/en-us/news/game-updates/) | 匹配的官方原画、新皮肤记录及明确的上线日期 |

Wiki 是皮肤身份主目录。官网名称规范化后精确匹配才合并；国服资料通过英雄及海报编号关联。未匹配的名称或等级保留英文或未知状态，不逐款补配置。来源别名由程序自动读取官网标签。

等级采用国服分类，因为当前 Wiki 与国际服英雄目录没有完整的替代等级资料。系列、炫彩颜色的中文翻译和图标映射属于显示资源，不决定版本或日期。

项目不维护逐款人工版本、日期、名称别名或视频链接覆盖表。SkinSpotlights 仅提供独立的视频浏览链接，不参与皮肤身份或上线依据判断。

| 仓库文件 | 内容 |
| --- | --- |
| [data/skins.json](data/skins.json) | 自动生成的皮肤快照、分组、元数据、来源链接与诊断信息 |
| [data/verification_report.json](data/verification_report.json) | 自动生成的待确定、推断和地区记录及其依据 |
| [data/skin_spotlights.json](data/skin_spotlights.json) | 自动收集的视频标题与编号 |
| [data/translations.json](data/translations.json) | 系列的中文显示翻译 |

## 日期与版本归属

优先采用 Wiki 版本页和官方公告中的新皮肤直接记录。返场、炫彩和重做提及不作为首发依据。没有直接记录时，符合条件的上线日期可以按无歧义的补丁时间线推断，并标为“推断”；依据缺失或冲突时保留“版本待确定”。日期推断可能继承上游日期错误，不代表官方确认。

程序自动解析支持格式中的官方列表、表格、排位奖励、活动和通行证明确日期。仅属于预告的日期不会直接将公告所属版本作为皮肤首发版本。来源原日期与冲突信息保留供核对，不逐款写入人工更正值。

Wiki 补丁日期与官方公告日期相差超过 7 天时，补丁日期留空并记录差异。这是项目的一致性规则，不代表已经独立确认实际补丁上线时间。

UPCOMING 和来源明确标为国服限定的记录不计入主目录总数。国服限定的目录日期不当作国际服上线日期。Upcoming 条目允许随上游更改或撤回；其他已有目录身份受保护，不能无故移除。“版本数”只计算有编号的补丁分组。

## 本地运行

需要 Python 3.10 或更新版本，以及 [uv](https://docs.astral.sh/uv/)。项目运行时仅使用 Python 标准库。

在仓库根目录运行：

~~~console
uv sync
uv run site-build
uv run python -B -m http.server 8001 --bind 127.0.0.1 --directory dist
~~~

打开 <http://127.0.0.1:8001>。构建读取已保存的皮肤和视频数据，将静态网站写入已忽略的 `dist/` 目录。构建不请求上游服务；网页中的外部图片仍需要网络。

## 更新数据

刷新皮肤来源和近期视频，检查后重新构建：

~~~console
uv run skin-update
uv run python -B -m wild_rift_skin_version.spotlights
uv run python -B -m unittest discover -s tests -q
uv run site-build
~~~

更新器抓取 Wiki 目录与文件、官方英雄页和编号补丁公告，以及国服目录。完整候选快照通过校验后，逐个原子替换有变化的文件。Wiki 请求间隔发送，遇到限流时有限次退避重试；抓取或解析失败不会覆盖已保存的皮肤快照。

使用已有响应缓存重建，不发出网络请求：

~~~console
uv run skin-update --cached
~~~

此命令需要本地已有完整的 `.cache/`。它复用记录的抓取时间，不伪造新的在线同步时间。自动生成的皮肤数据与核对报告不应手工修改。

## 视频链接

“视频”按钮打开对应的 [SkinSpotlights Wild Rift](https://www.youtube.com/@SkinSpotlightsWildRift) 视频。匹配依据为规范化标点后的英文完整皮肤名，不做模糊或逐款人工匹配。未匹配的皮肤不显示按钮，视频不嵌入或自动播放。

日常更新将公开频道订阅源合并到已保存目录，无需 API 密钥。订阅源只覆盖近期上传，不能保证完整覆盖，也不会自动发现旧视频转为私密或被删除。长时间中断后可能需要重新完整导入。

使用 `yt-dlp --flat-playlist -J` 导出的完整频道目录可以这样导入：

~~~console
uv run python -B -m wild_rift_skin_version.spotlights --import-catalog PATH
uv run site-build
~~~

将 `PATH` 替换为导出的 JSON 文件。yt-dlp 是可选导入工具，不是项目运行依赖。

## 自动化与部署

[GitHub Actions 工作流](.github/workflows/pages.yml) 将 `dist/` 构建并部署到 GitHub Pages，支持仓库子路径。

| 触发方式 | 行为 |
| --- | --- |
| 推送到 `main` | 测试、构建并部署已保存的数据，不重新抓取来源 |
| 每天纽约时间 12:34（`America/New_York`） | 测试、构建并部署；距上次成功数据同步至少 20 小时时，同时刷新来源 |
| 手动运行 | 可选择是否先刷新来源，再测试、构建和部署 |

启用刷新时，有变化的生成 JSON 会自动提交回 `main`。SkinSpotlights 更新是独立步骤；失败时保留已有视频目录，不阻碍皮肤更新和部署。

网页“更新”时间取皮肤快照时间与成功核心同步完成时间中较新的值。本地构建默认使用已保存的快照时间，也可通过 `WR_DATA_UPDATED_AT` 提供实际发生的较新同步完成时间。

在[手游仓库](https://github.com/syy674998887/wild-rift-skin-version)的 **Settings → Pages** 中选择 **GitHub Actions**，确认仓库允许工作流写入后运行工作流。部署成功后，工作流的部署任务会显示 Pages 网址。

## 开发

运行已有测试：

~~~console
uv run python -B -m unittest discover -s tests -q
~~~

现有 Python 测试不覆盖浏览器交互。修改前端后，检查窄屏布局、筛选与网址状态恢复、版本导航、图片切换、键盘关闭与焦点恢复，以及图片加载失败时的显示。

前端为 `site/` 中的原生 HTML、CSS 和 JavaScript。Python 模块位于 `src/wild_rift_skin_version/`，`skin_update.py` 和 `build_site.py` 是仓库本地入口。生成的网站、响应缓存和本地虚拟环境已被 Git 忽略。

## 许可

原创代码与文档采用 [MIT License](LICENSE)。界面改编自同一作者的 League Skin Version。第三方游戏数据、原画、视频、名称和商标不因此重新授权；详见[第三方声明](THIRD_PARTY_NOTICES.md)。
