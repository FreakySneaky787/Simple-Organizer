# Contributing to Simple Organizer

Thanks for wanting to help! Bug reports, ideas and pull requests are all welcome.

## Report bugs

- Use the [bug report form](https://github.com/FreakySneaky787/Simple-Organizer/issues/new/choose).
- Please attach `error.log` if there is one:
  - Windows: `%APPDATA%\simple_organizer\error.log`
  - Linux: `~/.local/share/simple_organizer/error.log`
- Say which version you use and how you installed it (Windows .exe, .deb or from source).

## Questions and ideas

- Questions and help: [Discussions](https://github.com/FreakySneaky787/Simple-Organizer/discussions)
  and the [Wiki](https://github.com/FreakySneaky787/Simple-Organizer/wiki).
- Ideas: the [feature request form](https://github.com/FreakySneaky787/Simple-Organizer/issues/new/choose).

## Code and pull requests

- **Open an issue first** for anything bigger than a small fix, so we can agree on it before you spend time on it.
- Run from source with Python 3.10+ and Tkinter: `python3 main.py` (see the [README](README.md)).
- Run the tests before opening a pull request: `python3 tests/run_all.py`
- The app uses the **Python standard library only** – please don't add dependencies.
- Safety first: Simple Organizer must never delete or overwrite a user's file, and every run must stay undoable.
- Keep pull requests small and about one thing. Code, comments, UI text and docs are in **English**.

## Code of conduct

Please be kind and respectful – see the [Code of Conduct](CODE_OF_CONDUCT.md).
By contributing you agree that your contribution is licensed under the [MIT License](LICENSE).
