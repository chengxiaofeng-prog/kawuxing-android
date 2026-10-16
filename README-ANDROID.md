# 卡五星 · 安卓版（Kivy）

把桌面版 `KaWuXing.exe` 转成安卓 APP 的完整工程。

- **规则 100% 同源**：`kawuxing/rules.py` + `kawuxing/engine.py` 直接复用桌面版引擎
    
  （84 张牌、屁胡只能自摸、亮倒者可点炮、抢杠只限补杠、杠上炮只算第一张、
    
  杠后按结构位判断听牌/亮倒、亮倒必须「进张后、出牌前」亮 —— 全部口径与桌面版一致）。
- **界面**：Kivy 触屏重写（点牌选中 → 再点打出；胡/杠/碰/过/亮倒/托管 都是屏幕按钮；
    
  选中任意手牌自动显示「打这张听什么、各剩几张」的推演）。
- **打包**：本机不需要装任何安卓环境，推到云端后自动编译 APK。

> **两条打包路线，任选其一（工程文件同一份）：**
>
> | 路线             | 说明                                       | 快速指引                                   |
> | -------------- | ---------------------------------------- | -------------------------------------- |
> | **腾讯 CNB（推荐）** | 微信扫码登录、**国内直连**、不需要加速工具                  | 看 **[`README-CNB.md`](README-CNB.md)** |
> | GitHub Actions | 需要能访问 github.com，常要 hosts / Watt Toolkit | 看下面的「从零到装上手机」                          |
>
> 如果你的网络打不开 GitHub，**直接用 CNB**，别折腾网络。

## 目录结构

✅ **本地 git 仓库已经建好并提交完成**（`Android/.git`），  
你只需要在平台上建个空仓库，然后双击对应的推送脚本即可。

```
Android/
├─ main.py                  Kivy 触屏版主程序（整局流程 + 自绘牌桌）
├─ kawuxing/rules.py        规则内核（与桌面版同一份）
├─ kawuxing/engine.py       牌局引擎 + 电脑对手（与桌面版同一份）
├─ buildozer.spec           打包配置（横屏、arm64、中文名「卡五星」）
├─ icon.png / presplash.png 图标与启动图（tools/gen_assets.py 生成）
├─ .gitignore               排除 __pycache__ / .buildozer / 字体等
├─ .cnb.yml                 CNB 流水线配置（国内直连，推荐）
├─ .github/workflows/android.yml   GitHub Actions 工作流（备用）
└─ tools/
   ├─ push_to_cnb.bat       双击即推送代码到 CNB（国内直连，推荐）
   ├─ push_to_github.bat    双击即推送代码到 GitHub
   ├─ check_cnb_yml.py      校验 .cnb.yml 语法
   ├─ fix_github_hosts.bat  打不开 github.com 时的一键 hosts 修复
   └─ gen_assets.py         重新生成图标 / 启动图
```

## 从零到装上手机（不需要写代码）

> ⚠️ **打不开 github.com？别往下看了，直接走 CNB 方案 —— 看 [`README-CNB.md`](README-CNB.md)，
>   
> 微信扫码、国内直连，3 步出包。** 下面这套只在你能正常访问 GitHub 时用。

### 1. 注册 GitHub 账号（免费，5 分钟）

> 前提：能打开 <https://github.com> 。打不开先看后面「GitHub 打不开怎么办」那一节。

1. 浏览器打开 <https://github.com> ，点右上角 **Sign up**；
2. 依次填：
   - **Email**：你自己的邮箱（QQ 邮箱、163、Gmail 都行，建议用常用的，后面要收验证码）；
   - **Password**：至少 8 位，**必须含数字和字母**（如 `KaWu2026xing`），太简单的密码会被反复打回；
   - **Username**：用户名，英文/数字/连字符，不能有空格和中文，**注册后改起来很麻烦，想好再填**
       
     （建议如 `zhangsan2026`，别用 `admin`、`test` 这类被占用的）；
   - **国家/地区**：选 **China**，勾选邮件订阅可不勾；
3. 点 **Create account** → 它会让你做个「拼图/旋转图形」的人机验证 → 通过后**去邮箱收验证码**，
     
   填进页面（验证码 15 分钟内有效，找不到就看垃圾邮件）；
4. 邮箱验证完成后会进一个「欢迎问卷」，全部可以点 **Skip personalization / Continue** 跳过，
     
   最后点 **Continue as free**（免费版完全够用，不需要付费）；
5. 进到首页看到右上角是你的头像，说明注册成功。

**注册后建议顺手做的两件事**（不做也能用，但能省后面的麻烦）：

- **把界面语言切成中文**：右上角头像 → **Settings** → 左侧 **Appearance** → **Preferred language**
    
  选 `中文(简体)` → 保存，页面会刷新成中文；
- **开启两步验证（可选）**：Settings → Password and authentication → Two-factor authentication。
    
  GitHub 有时会强制要求，提前开好省得后面被打断；手机装个验证器 App 扫码即可。

> 收不到验证码 / 一直转圈：换手机热点再试一次；密码老是被拒就换成「大小写字母 + 数字 + 符号」的组合。
>   
> 账号名一旦被占用就换一个，别纠结。

### 2. 把代码推上 GitHub（三选一）

> **重要：先在网页上建一个空仓库**——打开 <https://github.com/new> ，
>   
> Repository name 填 `kawuxing-android`，**不要勾** "Add a README file" / ".gitignore" / "license"
>   
> （勾了会让后面的推送冲突），Create repository。建好后页面停在 <https://github.com/你的用户名/kawuxing-android> 。

**方式 A · 双击脚本（最省事，推荐）**

本机已经装好 git 和浏览器登录组件了。直接**双击** `Android/tools/push_to_github.bat`：

1. 窗口问你的 GitHub 用户名 → **直接回车**（脚本已预设为本机的 `chengxiaofeng-prog`，
     
   用别的账号才需要手动输入）；
2. 问仓库名 → **直接回车**（默认 `kawuxing-android`）；
3. 中间会 pause 一次提醒你「网页上建好空仓库了吗」，按任意键继续；
4. 第一次推送会**弹出浏览器窗口让你登录 GitHub**（这是 Git Credential Manager，
     
   正常现象），点 Authorize 授权一次以后就不用再登了；
5. 看到 `[OK] Code is on GitHub` 就成功了，接着按下面第 3 步去 Actions 页等打包。

> 本地仓库已经建好并提交完成了：`Android/.git`，3 次提交、13 个文件，
>   
> **提交作者已设为本机的 GitHub 身份**（`chengxiaofeng-prog`），推上去会正确归到你名下。
>   
> 推送失败时脚本会打印三种常见原因，照着排查即可。

> ⚠️ **浏览器能开、git 推不上去？** 多半是加速工具只代理了浏览器。
>   
> 在 Watt Toolkit 的「网络加速」设置里看它的本地端口（通常是 26561），然后执行：
>   
> `git config --global http.proxy http://127.0.0.1:26561`
>   
> 想撤销：`git config --global --unset http.proxy`

**方式 B · GitHub Desktop 图形工具**

想用图形界面就先装 GitHub Desktop：

- 命令行安装：`winget install --id GitHub.GitHubDesktop -e`（本机已尝试，若卡住就说明
    
  下载源 github.com 不通，先解决网络，见后面那节）；
- 或者去 <https://desktop.github.com> 下载安装包。

装好后：`File → Add local repository` → 选 `KaWuXing3D\Android` 目录 →  
`Publish repository`（勾上 Keep this code private 保持私有）。  
**注意它只能"添加已有仓库"，不要用 New repository**（会和已有的 .git 打架）。

**方式 C · 纯命令行**

```bash
cd KaWuXing3D/Android
git remote add origin https://github.com/你的用户名/kawuxing-android.git
git push -u origin main
```

（`git init` / `add` / `commit` 已经做完了，不用再执行。）

### 3. 云端自动打包

1. 打开仓库的 **Actions** 标签页（第一次推送后自动开始跑）；
2. 首次编译约 **20～40 分钟**（要下载安卓 SDK/NDK），第二次起缓存生效只要几分钟；
3. 跑完后进入该次运行页面，底部 **Artifacts** 里有 `KaWuXing-APK`，点它下载 zip，
     
   解压得到 `KaWuXing-*.apk`（`debug` 版，可直接安装）。

> 字体说明：工作流会自动下载 Noto Sans SC（OFL 开源许可）打进 APK，
>   
> 安卓没有中文字体的话界面文字会显示方块，这一步保证了中文正常显示。
>   
> 下载源备了三个（jsDelivr → Google Fonts → GitHub raw），全部失败才会中断构建。

**构建失败怎么看**：Actions 里那次运行会有红叉 → 点进去 → 左边展开红色那一步，  
把报错那几行截图发我。常见原因：

| 现象                                          | 原因 / 处理                                     |
| ------------------------------------------- | ------------------------------------------- |
| `No such file or directory: buildozer.spec` | 仓库里 `buildozer.spec` 不在根目录（应和 `main.py` 并列） |
| 卡在 `Installing/Updating SDK` 很久             | 正常，首次要下 SDK/NDK 约 2GB；超过 40 分钟再看            |
| 红色步骤是「下载中文字体」                               | 三个源都被拦了，重跑一次（Actions 页面右上 Re-run jobs）      |
| `Permission denied` / 需要密码                  | 推送时用的是别的账号，检查仓库是不是你自己的                      |

### 4. 装到手机

1. 把 apk 传到手机（微信文件传输助手 / 数据线 / 网盘都行）；
2. 点开安装，系统提示「未知来源应用」时选择**允许**（设置里给该应用授权）；
3. 打开后横屏进入牌桌，你就是南位（下方），左右两家是电脑。

## GitHub 打不开怎么办（国内网络）

打不开多半不是你的问题，而是网络对 GitHub 的 HTTPS 连接做了干扰  
（现象：域名能解析、ping 也通，但浏览器显示「无法访问此网站」）。按下面顺序试：

**第 0 步 · 30 秒自检（先做这个）**

- 换个浏览器或用「无痕窗口」打开 github.com；
- 用**手机热点**（4G/5G 共享给电脑）打开 github.com ——
    
  如果热点能开、宽带打不开，说明是当前宽带/路由器的问题，换网络或用下面的加速工具。

**第 1 步 · 一键改 hosts（免安装，脚本已备好）**

双击 `tools/fix_github_hosts.bat` → 右键选择**以管理员身份运行**。  
它会把 GitHub 的真实 IP 写进 hosts 并刷新 DNS（原文件会备份为 `hosts.kawuxing.bak`，  
不想要了删掉脚本写入的那段即可）。跑完再刷新 github.com 试试。

**第 2 步 · 装 Watt Toolkit 一键加速（最有效）**

打开**微软商店**（Microsoft Store），搜索 **Watt Toolkit**（原名 Steam++）安装，  
启动后勾选「网络加速 → GitHub」并点击「一键加速」，然后刷新 github.com。  
它是本地反向代理，能绕过单纯改 hosts 解决不了的那种拦截。

**第 3 步 · 还是不行就换国内云构建**

把工程推到**腾讯 CNB（cnb.cool）**——微信扫码登录、国内直连、有免费构建额度，  
流水线配置我可以直接帮你写好，不需要任何加速工具。到时说一声即可。

> 小结：能访问 GitHub 就用 GitHub Actions（本文下面的步骤）；
>   
> 完全访问不了就用国内平台，两条路的工程文件是同一份。

## 玩法与操作

| 操作            | 说明                                    |
| ------------- | ------------------------------------- |
| 点手牌           | 选中（牌上浮），同时显示「打它听什么、各剩几张」              |
| 再点同一张         | 打出这张                                  |
| 胡 / 杠 / 碰 / 过 | 屏幕底部按钮，出现时机与桌面版一致                     |
| 亮倒            | 「进张后、出牌前」（手里多一张、且有牌打了仍听头）时出现按钮；亮倒后**出牌仍由自己点**，只能打「打了仍听头」的牌，想托管再点一下状态灯（亮倒后不能碰牌） |
| 继续 / 重开       | 结算后点「继续下一局」；右上角「重开」随时重开               |

规则要点（与桌面版完全一致）：

- 屁胡只能自摸；**亮倒的人可以点炮胡（含屁胡）**，未亮倒不受影响；
- **抢杠只限补杠**（加杠），暗杠、明杠不可抢；
- 杠上炮只算杠后补摸打出的第一张；
- 杠后照样能听牌（按 3×副露+手牌 的结构位判断）；亮倒只在**进张后、出牌前**（结构位 = 14）才亮得起来，
  暗杠完那一瞬是 13 位「等摸牌」，不能亮，补摸一张后才能亮；

## 后续怎么改规则 / 更新版本

桌面版改完规则后，把这两个文件覆盖过来再推一次即可：

```
KaWuXing3D/Desktop/kawuxing/rules.py  →  Android/kawuxing/rules.py
KaWuXing3D/Desktop/kawuxing/engine.py →  Android/kawuxing/engine.py
```

GitHub Desktop 里 Commit + Push，Actions 自动出新一版 APK。

## 本机预览（可选，开发用）

电脑装好 kivy 后可直接跑：

```bash
pip install kivy==2.3.0
cd KaWuXing3D/Android
python main.py        # 1280x720 横屏窗口
```

## 已知限制（第一版触屏版）

- 开局摇色子/理牌动画、牌墙取牌动画是桌面版特性，触屏版第一版从简（只保留节奏停顿）；
- 牌面为程序化简化绘制（筒=饼点、条=竹棍、中发白=字），与桌面版「最大化图案」不同源；
- 音效未接入。
