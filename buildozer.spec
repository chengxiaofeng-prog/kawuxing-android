[app]
# 卡五星 —— 安卓版打包配置（buildozer）
title = KaWuXing
package.name = kawuxing
package.domain = org.kawuxing
package.version = 1.0.0

# buildozer 1.5 起强制要求 [app] version 或 version.regex 二者之一，
# 只写 package.version 会报 "One of "version" or "version.regex" must be set"
version = 1.0.0

# 仓库根目录就是源码目录
source.dir = .
source.include_exts = py,png,jpg,kv,otf,ttf
# .git 一定要排除，否则整个版本库会被打进 APK
source.exclude_dirs = tools,.github,bin,.git,.buildozer,__pycache__
source.exclude_patterns = *.md,*.spec,LICENSE,prebuild.sh

# 版本号显式写死（不依赖 main.py 里的 __version__）

# 横屏 + 全屏（麻将牌桌横向布局）
orientation = landscape
fullscreen = 1

# 图标与启动图
icon.filename = icon.png
presplash.filename = presplash.png

# 依赖：纯 Python3 + Kivy（规则引擎零第三方依赖）
# 不锁 Kivy 小版本：python-for-android 对「不指定版本」的组合测过最多，
# 锁 kivy==2.3.0 反而可能和 p4a 内置的 Python 版本对不上。
requirements = python3,kivy

# 只编 arm64（2019 年以后的安卓手机基本都是），打包快一倍；
# 要兼容很老的手机改成 arm64-v8a,armeabi-v7a
android.archs = arm64-v8a
android.api = 34
android.minapi = 24
android.ndk_api = 24

# 应用名显示为中文
android.app_name = 卡五星

# 保持屏幕常亮
android.wakelock = True

# 自动接受 SDK 许可，避免云端构建卡在交互提示
android.accept_sdk_license = True

# 不需要备份/权限
android.allow_backup = False
android.permissions =

[buildozer]
log_level = 2
warn_on_root = 1
