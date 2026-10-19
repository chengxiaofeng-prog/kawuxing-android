[app]
# 卡五星 —— 安卓版打包配置（buildozer）
title = KaWuXing
package.name = kawuxing
package.domain = org.kawuxing
package.version = 1.5.0

# buildozer 1.5 起强制要求 [app] version 或 version.regex 二者之一，
# 只写 package.version 会报 "One of "version" or "version.regex" must be set"
version = 1.5.0

# ★ python-for-android 固定到官方正式版（2026-05-09）。
#   默认是跟 master 走 —— 上游随时会变，同一份配置今天能过、明天就挂。
#   v2026.05.09 是两年多来首个正式 release，含 Kivy/Python 版本兼容修复。
p4a.branch = v2026.05.09

# 仓库根目录就是源码目录
source.dir = .
source.include_exts = py,png,jpg,kv,otf,ttf,wav
# .git 一定要排除，否则整个版本库会被打进 APK
source.exclude_dirs = tools,.github,bin,.buildozer,__pycache__
source.exclude_patterns = *.md,*.spec,LICENSE,prebuild.sh,*.txt

# 横屏 + 全屏（麻将牌桌横向布局）
orientation = landscape
fullscreen = 1

# 图标与启动图
icon.filename = icon.png
presplash.filename = presplash.png

# ── 依赖 ──────────────────────────────────────────────────────────────
#
# ★★ 必须把目标 Python 锁到 3.11.9 ★★
#   p4a 正式版默认编译 Python 3.14，但 kivy recipe 拉的是 Kivy 2.3.1，
#   而 Kivy 2.3.1 官方只支持 Python 3.8 ~ 3.12。p4a 只用一个
#   no-ast-str.patch 让它「能编译通过」，运行时并不真正兼容。
#   症状：构建 100% 成功、APK 能安装，但一打开就闪退
#         （2026-10-15 实测，装了能上、点开就退）。
#   python3 与 hostpython3 版本必须一致，
#   否则 p4a 的 hostpython3.download() 会直接抛错。
#
# charset-normalizer 必须锁 <3.5：
#   它是 kivy -> requests 的传递依赖（纯 Python）。3.5.0 起该包开始发布
#   android 专用轮子（...-cp3xx-cp3xx-android_24_arm64_v8a.whl）。
#   p4a 先用 `pip --dry-run --platform=android_24_arm64_v8a --only-binary=:all:`
#   探测出这个轮子、把「直链 URL」写进 requirements.txt，随后真正安装
#   那条命令不带 --platform，于是报
#   "charset_normalizer-3.5.2-...-android_24_arm64_v8a.whl is not a supported
#    wheel on this platform" 而整轮构建失败（2026-10-14 连续两次都栽在这）。
#   3.4.9 及以前只有 py3-none-any 通用轮子，探测与安装都能通过。
requirements = python3==3.11.9,hostpython3==3.11.9,kivy,charset-normalizer==3.4.9

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
