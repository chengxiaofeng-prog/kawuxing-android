# 卡五星 · 安卓版 —— 用腾讯 CNB 打包 APK（国内直连，不需要 GitHub）

CNB（cnb.cool）是腾讯的云原生构建平台：**微信扫码登录、国内直连、免费额度足够**，  
不需要 GitHub、不需要任何加速工具。你的网络打不开 GitHub，就用这条路。

> 工程文件是同一份，`Android/` 文件夹同时带了 GitHub 和 CNB 两套打包配置，  
> 哪边方便用哪边。GitHub 版说明见 `README-ANDROID.md`。

---

## 目录结构（CNB 相关部分）

```
Android/
├─ .cnb.yml                ★ CNB 流水线配置（推上去就自动开始打包）
├─ main.py                  Kivy 触屏版主程序
├─ kawuxing/rules.py        规则内核（与桌面版同一份）
├─ kawuxing/engine.py       牌局引擎 + 电脑对手
├─ buildozer.spec           打包配置（横屏、arm64、应用名「卡五星」）
├─ fonts/NotoSansSC-Regular.ttf  ★ 中文字体子集（~200KB，已提交，构建期无需联网下载）
├─ icon.png / presplash.png 图标与启动图
└─ tools/
   ├─ push_to_cnb.bat       ★ 双击即推送代码到 CNB（本文件的主角）
   ├─ push_to_github.bat    备用：推送代码到 GitHub
   ├─ subset_font.py        从本机字体生成上面的字体子集（纯标准库）
   ├─ verify_font.py        用 GDI+ 渲染验证字体子集可用（纯标准库）
   ├─ check_cnb_yml.py      校验 .cnb.yml 语法（本地自检用）
   └─ fix_github_hosts.bat  备用：打不开 GitHub 时改 hosts
```

---

## 三步搞定

### 第 1 步 · 注册并建仓库（约 3 分钟）

1. 浏览器打开 **<https://cnb.cool>** ，点右上角登录，**用微信扫码**即可（无需邮箱验证）；
2. 首次登录会让你创建一个「组织」，名字随意（比如 `kawuxing`），创建完进入组织主页；
3. 点 **新建仓库**，仓库名填 **`kawuxing-android`**，  
   **可见性选「私有」**（源码不外发），**不要勾选**任何「初始化 README」之类的选项，  
   点创建。
   > 记下你的**用户名或组织名**，下一步要用。比如地址栏是  
   > `https://cnb.cool/kawuxing/kawuxing-android`，那用户名就是 `kawuxing`。

### 第 2 步 · 双击推送脚本

双击 `Android/tools/push_to_cnb.bat`，按提示操作：

1. 它会自动找 git —— **本机没装 Git for Windows 也没关系**，  
   脚本会自动改用 GitHub Desktop 里自带的那个 git（你机器上已经有了）；
2. 输入你的 **CNB 用户名/组织名** → 回车；
3. 仓库名 → **直接回车**（默认 `kawuxing-android`）；
4. 中间 pause 一次，按任意键继续；
5. 第一次推送会**弹出浏览器让你登录 CNB**，**微信扫码授权一次**，之后就不用再登了；
6. 看到 `[OK] Code is on CNB` 就成了。

### 第 3 步 · 等打包、下载 APK

1. 推送成功后**自动开始构建**。打开脚本最后打印的地址，或直接访问：  
   `https://cnb.cool/你的用户名/kawuxing-android/-/pipeline`
2. 首次约 **20～40 分钟**（要下载安卓 SDK/NDK），  
   之后因为有缓存（`/home/user/.buildozer`），几分钟就能出包；
3. 构建完成后，在该次构建页面的**附件**区域点 `KaWuXing-1.0.0-debug.apk` 下载；  
   也可以到仓库的「附件」列表里找（默认保留 90 天）；
4. 把 apk 传到手机安装（微信文件传输助手 / 数据线都行），  
   系统提示「未知来源应用」时选**允许**。

---

## 构建失败怎么看

流水线页面里每个步骤都能展开看日志。常见原因：

| 现象                          | 原因 / 处理                                          |
| --------------------------- | ------------------------------------------------ |
| 卡在 `Downloading SDK/NDK` 很久 | 正常，首次要下约 2GB，耐心等；有缓存后就没这一步了                      |
| 步骤「编译 APK」报 `No buildozer`  | 脚本会自动现场安装 buildozer（走清华镜像），日志里能看到，属正常            |
| 步骤「检查输入」报字体缺失               | 仓库里没提交 `fonts/NotoSansSC-Regular.ttf`，重新拉取最新代码再推 |
| `permission denied`         | 推送用的是别的账号，确认仓库是你刚建的那个                            |
| 找不到 `bin/*.apk`             | 看「编译 APK」步骤日志尾部的报错，把最后 30 行发我                    |

---

## 和 GitHub 方案的区别

|          | 腾讯 CNB            | GitHub Actions                  |
| -------- | ----------------- | ------------------------------- |
| 登录方式     | 微信扫码              | 邮箱注册 + 可能需加速工具                  |
| 国内访问     | 直连，无需加速           | 常需 hosts / Watt Toolkit         |
| 配置文件     | 根目录 `.cnb.yml`    | `.github/workflows/android.yml` |
| APK 在哪下载 | 构建页面的「附件」，保留 90 天 | 该次运行的 Artifacts，保留 90 天         |
| 免费额度     | 足够个人打包            | 公开仓库免费、私有仓库有额度                  |

两套配置都在仓库里，互不干扰，想用哪边推哪边即可。

---

## 后续怎么改规则 / 更新版本

桌面版改了规则后，把这两个文件覆盖过来，再跑一次 `push_to_cnb.bat` 就会自动出新包：

```
Desktop/kawuxing/rules.py   →   Android/kawuxing/rules.py
Desktop/kawuxing/engine.py  →   Android/kawuxing/engine.py
```

改版本号：编辑 `buildozer.spec` 里的 `package.version`。

---

## 本地预览（可选，开发用）

装了 Kivy 的话可以直接在电脑上跑触屏版看效果：

```bash
pip install kivy==2.3.0
cd Android
python main.py
```

电脑上鼠标点击等同于手机触屏操作。
