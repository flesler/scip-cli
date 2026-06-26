"""Tests for pure functions in scip_cli."""
import pytest
from scip_cli.lib import extract_leaf_name, infer_kind
from scip_cli.commands.search import parse_symbol, is_noisy_symbol


class TestExtractLeafName:
    def test_function(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/useDictation()."
        assert extract_leaf_name(s) == "useDictation"

    def test_class(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/UseDictationOptions#"
        assert extract_leaf_name(s) == "UseDictationOptions"

    def test_variable(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/someVar."
        assert extract_leaf_name(s) == "someVar"

    def test_type_literal_property(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/UseDictationOptions#typeLiteral0:onFallbackToRecording."
        assert extract_leaf_name(s) == "onFallbackToRecording"

    def test_class_member_property(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#config."
        assert extract_leaf_name(s) == "config"

    def test_method(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#damageHero()."
        assert extract_leaf_name(s) == "damageHero"

    def test_getter(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#`<get>aliveHeroes`()."
        assert extract_leaf_name(s) == "aliveHeroes"

    def test_setter(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#`<set>value`()."
        assert extract_leaf_name(s) == "value"

    def test_constructor(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#`<constructor>`()."
        assert extract_leaf_name(s) == "<constructor>"


class TestInferKind:
    def test_function(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/useDictation()."
        assert infer_kind(s) == "function"

    def test_method(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#damageHero()."
        assert infer_kind(s) == "method"

    def test_class(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/UseDictationOptions#"
        assert infer_kind(s) == "class"

    def test_variable(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/someVar."
        assert infer_kind(s) == "variable"

    def test_type_literal_property(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/UseDictationOptions#typeLiteral0:onFallbackToRecording."
        assert infer_kind(s) == "property"

    def test_getter(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#`<get>aliveHeroes`()."
        assert infer_kind(s) == "method"

    def test_constructor(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#`<constructor>`()."
        assert infer_kind(s) == "method"


class TestParseSymbol:
    def test_function(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/useDictation()."
        path, name = parse_symbol(s)
        assert path == "src/hooks/useDictation.ts"
        assert name == "useDictation()"

    def test_class(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/UseDictationOptions#"
        path, name = parse_symbol(s)
        assert path == "src/hooks/useDictation.ts"
        assert name == "UseDictationOptions#"

    def test_nested_path(self):
        s = "scip-typescript npm rovetia-app 1.2 src/components/ui/`btn.tsx`/Btn#"
        path, name = parse_symbol(s)
        assert path == "src/components/ui/btn.tsx"
        assert name == "Btn#"

    def test_no_backtick(self):
        assert parse_symbol("no-backticks-here") == ('?', '?')


class TestIsNoisySymbol:
    def test_file_level(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/"
        assert is_noisy_symbol(s) is True

    def test_type_literal_property(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/UseDictationOptions#typeLiteral0:onFallbackToRecording."
        assert is_noisy_symbol(s) is True

    def test_function_parameter(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/isNotSupportedError().(err)"
        assert is_noisy_symbol(s) is True

    def test_normal_function(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/useDictation()."
        assert is_noisy_symbol(s) is False

    def test_normal_class(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/UseDictationOptions#"
        assert is_noisy_symbol(s) is False

    def test_normal_method(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#damageHero()."
        assert is_noisy_symbol(s) is False
