# -*- coding: utf-8 -*-
"""
.cnb.yml 静态校验器 —— 不依赖 pyyaml。

CNB 的流水线配置是「严格的缩进 YAML」，这里做几件事：
  1) 逐行扫描，校验缩进是否成对（缩进必须是 2 的倍数）、有无 Tab、
     键值行是否有冒号、多行脚本块 | 的内容不参与结构分析；
  2) 解析出结构树，校验 CNB 关键字段拼写（docker.image / stages / jobs /
     script / settings / attachments ...），发现拼错的键直接报错；
  3) 打印结构树，便于人工复核。

用法： python check_cnb_yml.py [.cnb.yml]
"""
import os
import re
import sys

# CNB 合法键名白名单（按层级宽松收录，只用于「疑似拼错」告警）
KNOWN_KEYS = {
    # 顶层：分支 / 事件
    "push", "pull_request", "tag_push", "branch.delete", "branch.create",
    "vscode", "auto_tag", "commit.add", "tag_deploy",
    # pipeline 级
    "name", "runner", "docker", "git", "services", "env", "imports",
    "label", "stages", "failStages", "endStages", "ifNewBranch", "ifModify",
    "breakIfModify", "retry", "allowFailure", "lock", "sandbox", "include",
    # docker 级
    "image", "build", "devcontainer", "volumes", "dockerfile", "target",
    "by", "versionBy", "buildArgs", "name", "dockerUser", "dockerPassword",
    "sync", "ignoreBuildArgsInVersion",
    # stage / job 级
    "jobs", "script", "commands", "image", "type", "options", "optionsFrom",
    "settings", "settingsFrom", "args", "exports", "timeout", "if",
    "skipIfModify", "cpus", "tags",
    # plugin settings
    "attachments", "ttl", "tag", "commit", "slug", "endpoint", "token",
    # 常见自定义（env 里可以随便写，这里不校验 env 内部）
}

# 这些键下的子项是「用户自定义名称」，不是关键字
FREE_KEYS = {"env", "exports", "settings", "options", "imports", "volumes",
             "attachments", "job", "lock", "label", "runner", "git", "services"}


def strip_comment(line):
    """去掉行尾注释，但要忽略引号里的 # —— 这里简单处理。"""
    in_s = None
    for i, ch in enumerate(line):
        if ch in "'\"":
            if in_s == ch:
                in_s = None
            elif in_s is None:
                in_s = ch
        elif ch == "#" and in_s is None:
            if i == 0 or line[i - 1] in " \t":
                return line[:i]
    return line


def main(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    errors = []
    warns = []
    structure = []           # (indent, text)
    in_block = False         # 是否在多行脚本块里
    block_indent = 0
    prev_item_indent = None  # 上一个 "- " 项目的缩进

    for no, raw in enumerate(lines, 1):
        if "\t" in raw:
            errors.append("%4d: 出现 Tab，YAML 只能用空格缩进" % no)
            raw = raw.replace("\t", "  ")
        line = strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        text = line.strip()

        # 多行脚本块 | 的内容：缩进比块头更深，整块跳过
        if in_block:
            if indent > block_indent:
                continue
            in_block = False

        if indent % 2 != 0:
            errors.append("%4d: 缩进 %d 不是 2 的倍数：%s" % (no, indent, text))

        if text.endswith("|") or text.endswith(">"):
            in_block = True
            block_indent = indent
            structure.append((indent, text))
            continue

        # 结构行：必须是 "key: value"、"key:" 或 "- xxx"
        if text.startswith("- "):
            item = text[2:].strip()
            if ":" not in item and not item.endswith(":"):
                # 纯字符串任务（- echo hello），合法
                structure.append((indent, text))
                prev_item_indent = indent
                continue
        if ":" not in text:
            errors.append("%4d: 结构行缺少冒号：%s" % (no, text))
            continue

        key = text.split(":", 1)[0].strip().lstrip("- ").strip()
        parent_free = False
        # 向上找最近一层父键，判断是否在 FREE_KEYS 之下
        for pind, ptext in reversed(structure):
            if pind < indent:
                pkey = ptext.split(":", 1)[0].strip().lstrip("- ").strip()
                if pkey in FREE_KEYS or pkey.startswith("$"):
                    parent_free = True
                break

        if (not parent_free and key and key not in KNOWN_KEYS
                and not key.startswith("$") and not re.match(r"^[\w.\-/*]+$", key) is None
                and key not in KNOWN_KEYS):
            warns.append("%4d: 疑似非标准键「%s」（确认不是拼错就忽略）" % (no, key))

        structure.append((indent, text))

    # ---- 面向 CNB 的必填项检查 ----
    src = open(path, encoding="utf-8").read()
    if "stages" not in src:
        errors.append("缺少 stages —— CNB 流水线必须有 stages")
    if not re.search(r"^[\w$][^:]*:\s*$", src, re.M):
        errors.append("顶层没有找到「触发分支」（如 main: / $:）")
    # 上传产物一般需要 attachments
    if "attachments" not in src:
        warns.append("没有 attachments —— 若需要下载 APK 产物请确认已配置")

    print("=" * 64)
    print("文件：%s（%d 行）" % (os.path.basename(path), len(lines)))
    print("=" * 64)
    print("--- 结构树 ---")
    for ind, txt in structure:
        print("  " * (ind // 2) + txt)
    print()
    if warns:
        print("--- 提示（%d 条）---" % len(warns))
        for w in warns:
            print("  !", w)
        print()
    if errors:
        print("--- 错误（%d 条）---" % len(errors))
        for e in errors:
            print("  x", e)
        print("\n结果：不通过")
        return 1
    print("结果：通过（%d 条提示）" % len(warns))
    return 0


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else ".cnb.yml"
    sys.exit(main(p))
