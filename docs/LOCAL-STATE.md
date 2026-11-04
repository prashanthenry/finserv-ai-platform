# Local Terraform state on your Mac

Both projects use an explicit local backend:

```hcl
backend "local" {
  path = "terraform.tfstate"
}
```

Use the default Terraform workspace for this lab. With the provided `-chdir`
commands, the state files are separate:

| Project | State file relative to repository root |
| --- | --- |
| AWS | `aws/infra/terraform.tfstate` |
| Azure | `azure/infra/terraform.tfstate` |

No S3 bucket or Azure Blob account/container is used for Terraform state.
Provider lockfiles (`.terraform.lock.hcl`) are dependency records, not resource
state. Keep those lockfiles in Git.

## How responsibilities are divided

| Operation | Where it runs |
| --- | --- |
| Terraform format, schema validation and IaC security scans | Hosted GitHub Actions / ADO infrastructure validation pipelines |
| Infrastructure plan, apply, destroy, outputs and state management | Your Mac, in the same project folder |
| Application tests, training/evaluation, security checks, image push and Helm release | Hosted GitHub Actions for AWS / ADO for Azure |

Hosted jobs start with fresh filesystems and cannot see your Mac's local state.
The infrastructure definitions therefore have no live plan/apply jobs and do
not publish state as pipeline artifacts. After local provisioning, copy only
the documented non-secret resource names/IDs into application pipeline variables.
Application deployment does not need the Terraform state file.

## First provisioning from a fresh project

Authenticate to the chosen cloud and fill its `infra/terraform.tfvars` as
explained in SETUP.md. From the repository root, AWS commands are:

```bash
terraform -chdir=aws/infra init
terraform -chdir=aws/infra validate
terraform -chdir=aws/infra plan -out=release.tfplan
terraform -chdir=aws/infra show release.tfplan
terraform -chdir=aws/infra apply release.tfplan
bash aws/scripts/backup-state.sh
terraform -chdir=aws/infra output
```

For Azure:

```bash
terraform -chdir=azure/infra init
terraform -chdir=azure/infra validate
terraform -chdir=azure/infra plan -out=release.tfplan
terraform -chdir=azure/infra show release.tfplan
terraform -chdir=azure/infra apply release.tfplan
bash azure/scripts/backup-state.sh
terraform -chdir=azure/infra output
```

Review every plan before applying. Use the same cloud account/subscription and
the same local state directory for subsequent changes and teardown.

## Keep local backups

The helper copies the current state into the selected cloud folder's
`.state-backups/` directory using a unique timestamped filename. The backup
directory is restricted to its owner and backup files are readable/writable
only by that owner. Missing state produces an error rather than a fake backup.

```bash
bash aws/scripts/backup-state.sh
bash azure/scripts/backup-state.sh
```

Run the appropriate helper after each successful apply or destroy and before
maintenance. Keep an additional protected local/offline copy if you need
recovery from loss of the Mac's disk; a copy on the same disk does not cover
that event. State and saved plans can contain sensitive values. They are
excluded from Git and must not be uploaded as ordinary build reports.

Run one infrastructure operation at a time for each state. Local locking
protects operations on the same state file, not independent copies on other
machines. Do not delete state after provisioning or start updates from an
empty freshly extracted folder while the original resources still exist.
If you move the project, move its state and protected backups with it.

## If you already applied the previous remote-backend version

Do not start a new empty local state for resources already tracked elsewhere.
Preserve a state backup from the old initialized configuration and retain its
backend metadata/access while moving to the new local configuration. In that
same working directory, use:

```bash
terraform -chdir=infra init -migrate-state
terraform -chdir=infra state list
terraform -chdir=infra plan
```

Those commands assume your terminal is inside the appropriate `aws/` or
`azure/` folder. Review and answer Terraform's migration prompts, then verify
the expected resources and plan before continuing. `-reconfigure` does not
migrate existing state; do not use it as a substitute for migration. No state
migration or storage deletion was performed when this project was updated.

## Official references

* [Local backend](https://developer.hashicorp.com/terraform/language/backend/local)
* [Terraform initialization and state migration](https://developer.hashicorp.com/terraform/cli/commands/init)
