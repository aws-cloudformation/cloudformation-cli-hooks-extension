from rpdk.core.cli import main

class TestEntryPoint:
    def test_command_available(self, capsys):
        main(args_in=['hook'])
        out, err = capsys.readouterr()
        assert not err
        assert "--help" in out
        assert "hook subcommands" in out

    def test_command_without_required_args_fails(self, capsys):
        main(args_in=["hook", "--version"])
        out, err = capsys.readouterr()
        assert not err
        assert "cloudformation-cli-hooks-extension" in out
