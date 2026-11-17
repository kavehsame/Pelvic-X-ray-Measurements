# Contributing

Start with an issue describing the problem, expected behaviour and affected edition.
Use a synthetic or otherwise shareable example. Do not post patient images,
identifiers, annotation exports or screenshots containing confidential information.

For code changes, keep the Slicer extension tree intact. Update the web and Slicer
implementations together when a measurement definition, exported field or shared
workflow changes. UI-specific changes may affect only one edition; explain that
scope in the pull request. Add a regression test for a reproducible defect rather
than changing the reference output to make a failing comparison pass.

Read [development](docs/development.md) and [testing](docs/testing.md) for commands.
Update the relevant manual, release notes and model manifest when applicable.
Record which checks actually ran and any untested platforms or workflows. Clinical
validation and software regression tests answer different questions.

Contributions are submitted under this project's Apache License 2.0 unless clearly
identified otherwise. Preserve upstream notices and identify any new dependency.
