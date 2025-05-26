# sonar-config

Command line tool to entirely export or import a SonarQube Server or Cloud configuration.
The detail of what is exported or imported is listed at the bottom of this page

During import:
- When something (user, group, project, portfolio, application quality profile, quality gate, setting) does not exist in the target SonarQube Server or Cloud platform, the object is created
- When the object already exists it is updated according to the config file
- When an object exists in the target platform and is not defined in the config file, this object remains unmodified. As such the import of configuration is "additive" to the current config, it does not replace it.

## Requirements and Installation

`sonar-config` is installed through the **sonar-tools** [general installation](../README.md#install)

## Common command line parameters

`sonar-config` accepts all the **sonar-tools** [common parameters](../README.md#common-params)

## Usage

`sonar-config [-u <url>] [-t <token>] [-e|--export] [-i|--import] [-w|--what <configSelection>] [-f <file>] [-h] [-v <debugLevel>] [-k "<key1>,<key2>,...,<keyn>"]`

`--what` can be followed by a list of comma separated items to export or import
When `--what` is not specified, everything is exported or 

- `--what settings`: Exports/Import all global settings, permissions and permission templates
- `--what users`: Exports/Imports users (local or external). This automatically also exports/import groups to record group membership
- `--what groups`: Exports/Imports groups
- `--what rules`: Exports/Import customized rules, i.e. rules instantiated from rule templates and rules with custom tags and/or extended description
- `--what qualityprofiles`: Exports/Import quality profiles, including the inheritance scheme and profiles admin permissions. This automatically also exports customized rules that maybe be used in these quality profiles
- `--what qualitygates`: Exports/Imports quality gates, including quality gates admin permissions
- `--what projects`: Exports/Imports all projects settings. This can be a fairly long operation if there are a lot of projects
- `--what portfolios`: Exports/Imports all portfolios definition and settings. This can be a fairly long operation if there are a lot of portfolios
- `--what applications`: Exports/Imports all applications definition and settings. This can be a fairly long operation if there are a lot of applications
- `-f <file>`: Sends export to or read import from `<file>`, `stdout` for export and `stdin` for import is the default.
- `-k "<key1>,<key2>,...,<keyn>"`: Limits the export or import operation to projects, apps or portfolios matching these keys
- `--fullExport`: Will also export object properties that are not used for an import by may be of interest anyway
- `-h`: Displays help and exits
- `-u`, `-t`, `-h`, `-v`: See **sonar-tools** [common parameters](../README.md#common-params)

## Required Permissions

To export configuration, `sonar-config` needs a token with the global `Administer system` permission to export global settings, users, groups and permissions, as well as `Browse` permission on projects, apps and portfolios if export on these objects is requested
To import configuration, `sonar-config` needs a token with:
- The global `Administer system` permission to import global settings, users, groups, permissions permission templates
- `Create project, applications, portfolios` to import projects, portfolios and applications defnitions respectively
- `Administer quality profiles` and `Administer quality gates` to create quality profiles and quality gates respectively
- `Administer quality profiles` to create custome rules or modify existing ones (add custom tags or custom description)

## Example
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=squ_83356c9b2db891d45da2a119a29cdc4d03fe654e

# Export everything, send results to config.json in JSON format
sonar-config -e -f config.json

# Imports everything defined in config.json
sonar-config -i -f config.json

# Imports only data about project keys projectkey1, myprojectkey and anotherprojectkey 
sonar-config -i --what projects -k "projectkey1, myprojectkey, anotherprojectkey" -f config.json 

# Export global settings, users and groups, send results to stdout in JSON format (redirected in myconf.json)
sonar-config -e -w "settings, users, groups" >myconf.json

# Imports groups defined in myconf.json
sonar-config -i --what groups -f myconf.json 

# Imports nothing. From the myconf.json export above, projects are not exported.
sonar-config -i --what projects -f myconf.json 

```

## What is exported / imported

- Rules that are instantiations of rule templates
- Standard rules that have been modified with custom tags or extended description
- Quality profiles, including inheritance, and quality profiles admin permissions
- Quality gates, including quality gates admin permissions (SonarQube Server 9.3+)
- Groups
- Users and their group memberships
- Global permissions
- Permission templates
- All general settings (analysis scope, devops integration, general, governance, housekeeping, new code, SAST engine config, SCM; security, tech debt, If any 3rd party plugins global config)
- All languages settings
- Webhooks
- Projects configuration including settings if overridden from global settings, branch information, new code, QP, QG, links, permissions, webhooks, tags
- Portfolios configuration including definition (including project branches), permissions, report email frequency and targets
- Applications configuration including definition, permissions, tags and all branches definition)

Note that secrets are not exported (user passwords, tokens, webhooks secrets, devops integration secrets etc...)
And shall be fed manually after import

## Format

See sample export file [config.json](../test/config.json) that should cover the format for every single situation

