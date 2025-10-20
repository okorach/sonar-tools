# sonar-loc

Exports all projects lines of code as they would be counted by the commercial licences.
See `sonar-loc -h` for details

Basic Usage: `sonar-loc [-f <file>] [--format csv|json] [-a] [-n] [--withTags] [--withURL] [--apps] [--portfolios] [--topLevelOnly]`
- `-f`: Define file for output (default stdout). File extension is used to deduct expected format (json if file.json, csv otherwise)
- `--format`: Choose export format between csv (default) and json
- `--projects`: Output the LOC of projects (this is the default if nothing specified)
- `--apps`: Output the LOC of applications (Developer and higher editions)
- `--portfolios`: Output the LOC of portfolios (Enterprise and higher editions)
- `--topLevelOnly`: For portfolios, only output LoCs for top level portfolios (Enterprise Edition only)
- `-n | --withName`: Outputs the project or portfolio name in addition to the key
- `-a | --withLastAnalysis`: Output the last analysis date (all branches and PR taken into account) in addition to the LOCs
- `--withTags`: Outputs the tags of the project, app or portfolio
- `--withURL`: Outputs the URL of the project, app or portfolio for each record
- `-b`: Export LoCs for each branches of targeted objects (projects or applications)

## Required Permissions

`sonar-loc` needs `Browse` permission on all projects of the Server or Cloud instance

## Requirements and Installation

`sonar-loc` is installed through the **sonar-tools** [general installation](../README.md#install)

## Common command line parameters

`sonar-loc` accepts all the **sonar-tools** [common parameters](../README.md#common-params)
