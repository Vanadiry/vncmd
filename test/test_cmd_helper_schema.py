"""网页命令表 schema 与命令行、默认配置的一致性

doc/cmd_helper/schema.json 为手工维护，网页只读这一份。
这组测试负责在命令或配置改动后指出哪一处忘了同步。
"""

import argparse
import json
from pathlib import Path

import pytest

from vncmd.cli import _version_string, build_parser
from vncmd.core.defaults import CONFIG_TOML
from vncmd.core.schema import CONTENT_LETTERS, SCHEMA

SCHEMA_PATH = Path("doc/cmd_helper/schema.json")


def 读schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def 命令表(schema: dict) -> dict[str, dict]:
    return {" ".join(item["path"]): item for item in schema["commands"]}


def _jsonable(value):
    if value is argparse.SUPPRESS:
        return None
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return str(value)


def _action_kind(action) -> str:
    """把 argparse 的内部 action 名称转成与 schema.json 一致的稳定名称"""
    name = type(action).__name__.lstrip("_")
    return {
        "StoreAction": "store",
        "StoreTrueAction": "store_true",
        "StoreFalseAction": "store_false",
        "AppendAction": "append",
        "CountAction": "count",
        "HelpAction": "help",
        "VersionAction": "version",
        "SubParsersAction": "subparsers",
    }.get(name, name)


def _action_info(action) -> dict:
    item = {
        "kind": _action_kind(action),
        "dest": action.dest,
        "option_strings": list(action.option_strings),
        "help": action.help or "",
        "default": _jsonable(action.default),
        "required": bool(action.required),
        "nargs": _jsonable(action.nargs),
        "choices": _jsonable(list(action.choices))
        if action.choices is not None
        else None,
        "metavar": _jsonable(action.metavar),
    }
    type_name = getattr(action.type, "__name__", None)
    if type_name:
        item["type"] = type_name
    return item


def _usage_parts(text: str) -> list[str]:
    """把 usage 拆成可比较的片段

    argparse 的输出随 Python 版本变化：含位置参数的互斥组在 3.13 起写成
    [--check | value]，更早版本写成 [--check] [value]；选项的排列顺序也
    不一致。这里统一写法并排序，只比较内容。
    """
    return sorted(text.replace(" | ", "] [").split())


def _command_info(parser, path: list[str], summary: str = "") -> dict:
    positionals = []
    options = []
    subcommands = []

    for action in parser._positionals._group_actions:
        if isinstance(action, argparse._SubParsersAction):
            subcommands = list(action.choices)
            continue
        positionals.append(_action_info(action))

    for action in parser._optionals._group_actions:
        if isinstance(action, argparse._HelpAction):
            continue
        options.append(_action_info(action))

    groups = []
    for group in parser._mutually_exclusive_groups:
        names = []
        for action in group._group_actions:
            names.extend(action.option_strings)
        if names:
            groups.append(names)

    # --json 与 --download 的互斥在 main 里统一校验，不在 argparse 分组里
    by_dest = {action.dest: action for action in parser._optionals._group_actions}
    if "json" in by_dest and "download" in by_dest:
        groups.append(
            [*by_dest["json"].option_strings, *by_dest["download"].option_strings]
        )

    return {
        "path": path,
        "summary": summary,
        "description": parser.description or "",
        "usage": parser.format_usage().strip(),
        "positionals": positionals,
        "options": options,
        "groups": groups,
        "subcommands": subcommands,
    }


def 从命令行生成() -> dict:
    """按 parser 重新走一遍，供测试逐字段对比 schema.json"""
    parser = build_parser()
    commands = []

    def walk(current, path: list[str], summary: str = ""):
        commands.append(_command_info(current, path, summary))
        if current._subparsers is None:
            return
        for action in current._subparsers._group_actions:
            if not isinstance(action, argparse._SubParsersAction):
                continue
            helps = {item.dest: item.help or "" for item in action._choices_actions}
            for name, child in action.choices.items():
                walk(child, [*path, name], helps.get(name, ""))

    walk(parser, ["vncmd"])
    return {"commands": commands}


def 配置说明() -> dict[str, str]:
    """从默认配置模板的注释里取出每项说明"""
    result = {}
    section = ""
    comments = []
    for raw in CONFIG_TOML.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            comments = []
        elif line.startswith("#"):
            comments.append(line[1:].strip())
        elif "=" in line:
            key = line.split("=", 1)[0].strip()
            if comments:
                result[f"{section}.{key}"] = " ".join(comments)
            comments = []
    return result


class Test顶层结构:
    def test_schema文件存在(self):
        assert SCHEMA_PATH.is_file(), "网页的 schema.json 被删了"

    def test_是合法json(self):
        schema = 读schema()

        assert set(schema) == {"version", "commands", "config"}
        assert schema["commands"]
        assert schema["config"]

    def test_版本与命令行一致(self):
        version = _version_string()
        if version.startswith("vncmd "):
            version = version.removeprefix("vncmd ")
        assert 读schema()["version"] == version

    def test_命令路径不重复(self):
        paths = [tuple(item["path"]) for item in 读schema()["commands"]]

        assert len(paths) == len(set(paths))

    def test_配置路径不重复(self):
        paths = [item["path"] for item in 读schema()["config"]]

        assert len(paths) == len(set(paths))


class Test页面不写浏览器存储:
    """配置只保留在页面内存里，刷新即恢复默认值

    页面一旦引入任何浏览器存储，刷新后就会带回上次的配置。
    """

    def test_没有使用浏览器存储(self):
        html = Path("doc/cmd_helper/index.html").read_text(encoding="utf-8")

        for name in ("localStorage", "sessionStorage", "indexedDB", "document.cookie"):
            assert name not in html, f"页面用了 {name}，配置会留在浏览器里"

    def test_只读取同目录的schema(self):
        html = Path("doc/cmd_helper/index.html").read_text(encoding="utf-8")

        assert '"./schema.json"' in html


class Test命令与parser一致:
    def test_命令列表一致(self):
        schema_commands = 命令表(读schema())
        parser_commands = 命令表(从命令行生成())

        assert set(schema_commands) == set(parser_commands), (
            "schema.json 与命令行注册的子命令对不上，"
            f"多出 {sorted(set(schema_commands) - set(parser_commands))}，"
            f"缺少 {sorted(set(parser_commands) - set(schema_commands))}"
        )

    def test_每个命令的字段都一致(self):
        """逐字段比对，位置参数、选项、说明改了都要同步 schema

        requires、requires_any、required_one 与额外互斥组为网页补充的
        运行时约束，parser 里没有这些字段，单独校验。
        """
        schema_commands = 命令表(读schema())
        parser_commands = 命令表(从命令行生成())

        for name, expected in parser_commands.items():
            actual = schema_commands[name]
            actual = {
                key: value
                for key, value in actual.items()
                if key not in ("required_one", "required_one_exclusive")
            }
            actual["options"] = [
                {
                    key: value
                    for key, value in option.items()
                    if key not in ("requires", "requires_any")
                }
                for option in actual["options"]
            ]
            schema_groups = actual.pop("groups")

            expected = dict(expected)
            parser_groups = expected.pop("groups")

            actual_usage = actual.pop("usage")
            expected_usage = expected.pop("usage")

            assert actual == expected, f"{name} 与 schema.json 不一致"
            assert _usage_parts(actual_usage) == _usage_parts(expected_usage), (
                f"{name} 的 usage 与 schema.json 不一致"
            )
            assert all(group in schema_groups for group in parser_groups), (
                f"{name} 的 schema.json 缺少 argparse 的互斥组"
            )

    def test_额外互斥组也引用真实选项(self):
        """schema 可以补 argparse 表达不了的互斥关系"""
        tracker = 命令表(读schema())["vncmd tracker"]

        assert ["-j", "--json", "-f", "--fetch"] in tracker["groups"]

    def test_包含嵌套工具命令(self):
        commands = 命令表(读schema())

        assert "vncmd tool" in commands
        assert "vncmd tool check" in commands
        assert "vncmd tool embed-id" in commands
        assert commands["vncmd tool"]["subcommands"] == ["check", "cache", "embed-id"]


class Test互斥与依赖:
    @pytest.mark.parametrize("name", sorted(命令表(读schema())))
    def test_互斥组里的选项都存在(self, name):
        command = 命令表(读schema())[name]
        names = {
            option_string
            for option in command["options"]
            for option_string in option["option_strings"]
        }

        for group in command["groups"]:
            assert group, f"{name} 有空的互斥组"
            assert set(group) <= names, f"{name} 的互斥组 {group} 引用了不存在的选项"

    @pytest.mark.parametrize("name", sorted(命令表(读schema())))
    def test_requires引用的选项都存在(self, name):
        command = 命令表(读schema())[name]
        names = {
            option_string
            for option in command["options"]
            for option_string in option["option_strings"]
        }

        for option in command["options"]:
            for requirement in option.get("requires", []):
                assert requirement in names, (
                    f"{name} 的 {option['option_strings']} 依赖不存在的 {requirement}"
                )
            for group in option.get("requires_any", []):
                assert group, f"{name} 的 {option['option_strings']} 有空依赖组"
                for requirement in group:
                    assert requirement in names, (
                        f"{name} 的 {option['option_strings']} "
                        f"依赖不存在的 {requirement}"
                    )

    @pytest.mark.parametrize("name", sorted(命令表(读schema())))
    def test_required_one引用的选项和位置参数都存在(self, name):
        command = 命令表(读schema())[name]
        names = {
            option_string
            for option in command["options"]
            for option_string in option["option_strings"]
        }
        positional_count = len(command["positionals"])

        for alternative in command.get("required_one", []):
            if "option" in alternative:
                assert alternative["option"] in names, (
                    f"{name} 的必选项 {alternative['option']} 不存在"
                )
            if "positional" in alternative:
                assert 0 <= alternative["positional"] < positional_count, (
                    f"{name} 的必选位置参数 {alternative['positional']} 不存在"
                )

    def test_translate依赖lyric(self):
        song = 命令表(读schema())["vncmd song"]
        translate = next(
            option
            for option in song["options"]
            if "--translate" in option["option_strings"]
        )

        assert translate.get("requires") == ["--lyric"]

    def test_tracker的auto_accept与force依赖fetch(self):
        """CLI 里这两个修饰项离开 --fetch 会直接报错"""
        tracker = 命令表(读schema())["vncmd tracker"]

        for name in ("--auto-accept", "--force"):
            option = next(
                option
                for option in tracker["options"]
                if name in option["option_strings"]
            )
            assert option.get("requires") == ["--fetch"]

    def test_tracker的diff依赖download或json(self):
        tracker = 命令表(读schema())["vncmd tracker"]
        diff = next(
            option
            for option in tracker["options"]
            if "--diff" in option["option_strings"]
        )

        assert diff.get("requires_any") == [["-d", "--download", "-j", "--json"]]

    @pytest.mark.parametrize("name", ["vncmd album", "vncmd playlist"])
    def test_dlink依赖json(self, name):
        command = 命令表(读schema())[name]
        dlink = next(
            option
            for option in command["options"]
            if "--dlink" in option["option_strings"]
        )

        assert dlink.get("requires") == ["--json"]

    def test_互斥组与命令行一致(self):
        """schema 里的 groups 不能比 argparse 少，否则网页看不出冲突"""
        schema_command = 命令表(读schema())["vncmd song"]
        parser_command = 命令表(从命令行生成())["vncmd song"]

        assert schema_command["groups"] == parser_command["groups"]


class Test命令级必选项:
    def test_cookie需要值或check(self):
        cookie = 命令表(读schema())["vncmd cookie"]

        assert cookie["required_one"] == [
            {"option": "--check", "label": "--check"},
            {"positional": 0, "label": "Cookie 值"},
        ]
        assert cookie["required_one_exclusive"] is True

    def test_tool_cache需要stats或clear(self):
        cache = 命令表(读schema())["vncmd tool cache"]

        assert cache["required_one"] == [
            {"option": "--stats"},
            {"option": "--clear"},
        ]


class Test配置与默认配置一致:
    def test_配置项集合一致(self):
        schema_paths = [item["path"] for item in 读schema()["config"]]
        table_paths = [setting.path for setting in SCHEMA]

        assert schema_paths == table_paths, (
            "schema.json 的配置项与 core/schema.py 对不上，"
            f"多出 {sorted(set(schema_paths) - set(table_paths))}，"
            f"缺少 {sorted(set(table_paths) - set(schema_paths))}"
        )

    @pytest.mark.parametrize("setting", SCHEMA, ids=lambda item: item.path)
    def test_每一项的规则与默认值一致(self, setting):
        item = next(
            item for item in 读schema()["config"] if item["path"] == setting.path
        )

        assert item["kind"] == setting.kind
        assert item["values"] == list(setting.values)
        assert item["minimum"] == setting.minimum
        assert item["maximum"] == setting.maximum
        assert item["default"] == setting.default
        assert type(item["default"]) is type(setting.default)

    @pytest.mark.parametrize("setting", SCHEMA, ids=lambda item: item.path)
    def test_每一项都有说明(self, setting):
        item = next(
            item for item in 读schema()["config"] if item["path"] == setting.path
        )

        assert item["description"], f"{setting.path} 在网页上没有说明"

    def test_content配置给出三个复选框(self):
        """下载内容在网页上为音频、歌词、封面三个复选框"""
        item = next(
            item for item in 读schema()["config"] if item["path"] == "download.content"
        )

        assert item["kind"] == "content"
        assert [option["value"] for option in item["options"]] == list(CONTENT_LETTERS)
        assert all(option["label"] for option in item["options"])

    @pytest.mark.parametrize("setting", SCHEMA, ids=lambda item: item.path)
    def test_说明与默认配置注释一致(self, setting):
        descriptions = 配置说明()
        item = next(
            item for item in 读schema()["config"] if item["path"] == setting.path
        )

        assert item["description"] == descriptions.get(setting.path, ""), (
            f"{setting.path} 的说明与默认配置模板的注释对不上"
        )
