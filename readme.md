# SSL/TLS Certificate Automation Playbooks

## 1. Overview

These Ansible playbooks manage certificate requests, installation, activation, and rollback for Apache HTTPD and Tomcat servers.

Throughout this document, `<target>` represents the hostname of the server being modified. Replace placeholders before running commands; do not type angle brackets literally into unquoted shell commands.

### Systems and access

At least two machines are involved:

- **`ansible-as`:** The Ansible server where the playbooks are stored and executed.
- **`<target>`:** The managed server whose certificate is being updated.

**All playbooks are located on `ansible-as` in `/home/ansiblecontrol/sjf-ansible/cert`.**

Before running the playbooks, connect to the Ansible server, switch accounts, and enter the playbook directory:

```bash
# Connect to the Ansible server.
ssh ansible-as

# Switch to the account used to execute the playbooks.
sudo su - ansiblecontrol

# Enter /home/ansiblecontrol/sjf-ansible/cert.
cd sjf-ansible/cert

# Replace <your-userid> with your personal SSH userid for target servers.
export operator='<your-userid>'

# Replace <target> with the hostname. Retain the trailing comma.
export target='<target>,'
```

These are interactive instructions, not an unattended script. After each account or host transition, execute subsequent commands in the new shell.

The login shell for `ansiblecontrol` starts in `/home/ansiblecontrol`, so `cd sjf-ansible/cert` reaches the full directory above.

### People and responsibilities

- **Cert installer:** Runs the playbooks, submits the CSR through TDX, retrieves the issued certificate ZIP, stages it on `ansible-as`, and installs and activates the certificate.
- **Cert administrator:** A member of the **System Administrators** group who processes the CSR with the certificate authority and generally attaches the resulting ZIP to the TDX ticket before closing it.

### Workflow

1. On a new machine, install Python 3.11 using `install_python311.yml`.
2. If required, migrate the server using `migrate_to_current.yml` before or at the start of its certificate change.
3. Run `prepare_cert_request.yml`. It generates the CSR and emails it to the person running the playbook.
4. Create a TDX ticket with the CSR attached and direct it to **System Administrators**.
5. The cert administrator processes the request and generally attaches the signed certificate ZIP to the ticket and closes it.
6. Download that ZIP and place it in `/tmp/certzip` on **`ansible-as`**.
7. Run `identify_cert_zips.yml` to identify the associated target and rename the ZIP.
8. Run `install_cert.yml` in report-only mode, review the results, then apply to stage the certificate.
9. Run `activate_cert.yml` in report-only mode, review the results, then apply during the scheduled window.
10. Compare the before-and-after endpoint results and verify the served certificate. Investigate differences or roll back as necessary.

**Closing the TDX ticket completes certificate issuance, not deployment.** Production deployment requires a separate change request and off-hours scheduling.

## 2. Prerequisites and Command Conventions

### Python 3.11

The playbooks expect Python 3.11, except for `install_python311.yml`, which installs it. **Run this playbook first on a new machine.**

```bash
# Install Python 3.11 if needed.
ansible-playbook -i "${target:?Set target first}" install_python311.yml -u "${operator:?Set operator first}" -k -K
```

### Operator identity

`operator` must be the personal SSH userid of the person performing the change, not a fixed username and not the shared `ansiblecontrol` execution account.

- `-u` selects the SSH userid for target connections.
- `-k` prompts for the SSH password.
- `-K` prompts for the privilege-escalation password.
- A trailing comma makes a single hostname an inline Ansible inventory.

Commands below assume the access and environment setup in the overview has been completed. Local ZIP processing does not need the target SSH userid.

## 3. Migration to the `current` Symlink

Servers are being migrated to a method that avoids modifying Tomcat `server.xml` files for each certificate rotation. Application configuration references the stable `/etc/pki/java/current` path, and activation changes the symlink to select the active certificate generation.

- **`current`:** Active certificate generation.
- **`rollback`:** Previous generation available for recovery.

`migrate_to_current.yml` performs the one-time migration. It is not a routine requirement for servers already migrated. Plan migration changes and any associated reboot within the approved scope and window.

### Migration status

Already migrated:

- All development servers.
- All preproduction (`pprd`) servers.
- Production: `rhel-go`, `wordpress-prod`, and `rhelxess3-prod`.

Require migration before or at the start of the next certificate change:

- `rhelxead1-prod`
- `rhelxean`
- `rhelxeas1-prod`
- `rhelxess1-prod`
- `rhelxess2-prod`

This is the status supplied for this documentation; update it as migrations are completed.

```bash
# For a server requiring migration, preview first.
ansible-playbook -i "${target:?Set target first}" migrate_to_current.yml -u "${operator:?Set operator first}" -k -K

# Only after reviewing the preview, apply the required migration.
# Migration can reboot the server; use the approved window.
ansible-playbook -i "${target:?Set target first}" migrate_to_current.yml -u "${operator:?Set operator first}" -k -K -e migrate_apply=true
```

## 4. Playbook Reference

### `prepare_cert_request.yml` — Generate and email the CSR

Creates the pending certificate request material on `<target>` and emails the public CSR to the person running the playbook. Generating pending material does not activate it.

```bash
ansible-playbook -i "${target:?Set target first}" prepare_cert_request.yml -u "${operator:?Set operator first}" -k -K
```

Attach the emailed CSR to a TDX ticket directed to **System Administrators**. Do not attach private keys or keystores to tickets.

### `identify_cert_zips.yml` — Identify and rename CA ZIPs

CA ZIPs arrive with transaction-number filenames that do not identify their target. Place the returned archives in `/tmp/certzip` on `ansible-as`. This playbook inspects certificates inside each ZIP and can rename the archive so the associated target is clear.

```text
Before: /tmp/certzip/<transaction_number>.zip
After:  /tmp/certzip/<target>_<transaction_number>.zip
```

```bash
# Inspect without renaming.
ansible-playbook identify_cert_zips.yml -e rename_files=false

# Identify and rename.
ansible-playbook identify_cert_zips.yml -e rename_files=true
```

This is controller-side processing, not installation or activation on the target.

### `install_cert.yml` — Validate and stage

Validates and stages the signed certificate response for the pending generation. Installation does not switch `current`, restart services, or reboot the server.

```bash
# Report-only preview.
ansible-playbook -i "${target:?Set target first}" install_cert.yml -u "${operator:?Set operator first}" -k -K

# Apply staging after reviewing the preview.
ansible-playbook -i "${target:?Set target first}" install_cert.yml -u "${operator:?Set operator first}" -k -K -e cert_install_apply=true
```

### `activate_cert.yml` — Activate and verify

Validates the staged generation, preserves the previous active generation through `rollback`, changes `current` to the new generation, and reboots as required by activation. It incorporates endpoint checks at the beginning and end.

```bash
# Report-only preview.
ansible-playbook -i "${target:?Set target first}" activate_cert.yml -u "${operator:?Set operator first}" -k -K

# Apply during the scheduled outage window.
ansible-playbook -i "${target:?Set target first}" activate_cert.yml -u "${operator:?Set operator first}" -k -K -e cert_activate_apply=true
```

There is no need to execute `test.yml` explicitly during activation.

### `rollback_cert.yml` — Recover the previous generation

Defaults to report-only mode. Apply requires `cert_rollback_apply=true`. It points `current` directly to the directory resolved by `rollback`, leaving `rollback` unchanged. See the full Roll Back Plan below.

## 5. Production Change Requests

A change request is required for production servers: hostnames ending in `-prod` (including `wordpress-prod`) and `rhel-go`. Schedule production certificate changes **off hours**. Confirm the environment classification of any other production system before proceeding.

| Field | Required value |
|---|---|
| Type | Licensing & Compliance / SSL & Certificates |
| Data/Process Change Modifications | No |
| Is this a standardized change? | Yes |
| Change to be implemented | Copy the inline block below. |
| Test Plan | Copy the inline block below. |
| Roll Back Plan | Copy the inline block below. |

Under the described change-management workflow, selecting **Yes** for **Is this a standardized change?** results in automatic approval.

The following blocks are intended for copying into CR fields. All explanatory content is formatted as Bash comments; only commands appear without `#`. Markdown viewers control fonts: use a sans-serif font for surrounding prose in the destination editor if required. Code blocks normally render in monospace for command readability.

### Field: Change to be implemented

```bash
# CHANGE IMPLEMENTATION INSTRUCTIONS
# Execute interactively, one step at a time. Stop on unexpected results.
# Schedule production work off hours under the required change request.
# Retrieve the certificate through the associated CSR TDX ticket first.

# 1. ACCESS THE PLAYBOOKS ON ANSIBLE-AS
# All playbooks reside in /home/ansiblecontrol/sjf-ansible/cert.
# Run subsequent commands in the shell opened by each preceding login step.
ssh ansible-as
sudo su - ansiblecontrol
cd sjf-ansible/cert

# Set your personal SSH userid, not the shared ansiblecontrol account.
export operator='<your-userid>'
printf 'Ansible SSH userid: %s\n' "$operator"

# Select one target at a time; retain the trailing comma.
export target='<target>,'
printf 'Target inventory: %s\n' "$target"
ansible -i "${target:?Set target first}" all --list-hosts

# 2. VERIFY PREREQUISITES
# On a new machine, install Python 3.11 before other target playbooks.
# Run the following command if Python 3.11 installation is needed.
ansible-playbook -i "${target:?Set target first}" install_python311.yml -u "${operator:?Set operator first}" -k -K

# MIGRATION ONLY: Skip the next two commands if already migrated.
# For an unmigrated server, preview and review the migration first.
ansible-playbook -i "${target:?Set target first}" migrate_to_current.yml -u "${operator:?Set operator first}" -k -K

# MIGRATION ONLY: Apply after review, within the approved window.
# This can change application configuration and reboot the server.
ansible-playbook -i "${target:?Set target first}" migrate_to_current.yml -u "${operator:?Set operator first}" -k -K -e migrate_apply=true

# 3. RETRIEVE AND IDENTIFY THE CA RESPONSE
# Download the issued certificate ZIP from the CSR TDX ticket.
# Confirm it is the issued response, not the CSR or an unrelated attachment.
# Place it in /tmp/certzip on ansible-as; record the ticket number in the CR.
# Never place private keys in TDX tickets or response ZIPs.
# Identify and rename transaction-number ZIPs to make their target clear.
ansible-playbook identify_cert_zips.yml -e rename_files=true

# 4. PREVIEW INSTALLATION
# Confirm target identity, response ZIP, SANs, application profile, and
# pending generation. The certificate must match the pending CSR/key.
# Resolve all blockers before continuing.
ansible-playbook -i "${target:?Set target first}" install_cert.yml -u "${operator:?Set operator first}" -k -K

# 5. INSTALL WITHOUT ACTIVATION
# Require successful staging and validation before proceeding.
# This must not switch current, restart services, or reboot.
ansible-playbook -i "${target:?Set target first}" install_cert.yml -u "${operator:?Set operator first}" -k -K -e cert_install_apply=true

# 6. PREVIEW ACTIVATION AND RECORD THE ORIGINAL GENERATION
# Record this host's current generation in the change record for recovery.
ansible -i "${target:?Set target first}" all -u "${operator:?Set operator first}" -k -K -b -m ansible.builtin.command -a 'readlink -f /etc/pki/java/current'

# Review the activation preview and intended new generation.
# Investigate already-active results rather than assuming a new change.
ansible-playbook -i "${target:?Set target first}" activate_cert.yml -u "${operator:?Set operator first}" -k -K

# 7. ACTIVATE AND REBOOT DURING THE APPROVED WINDOW
# Activation preserves the former current generation through rollback,
# switches current, validates configuration, and performs the reboot.
# Integrated testing captures before-and-after endpoint results.
ansible-playbook -i "${target:?Set target first}" activate_cert.yml -u "${operator:?Set operator first}" -k -K -e cert_activate_apply=true

# 8. VERIFY BEFORE PROCEEDING TO ANOTHER HOST
# Compare endpoint results before and after activation.
# Some WAR-derived URLs are invalid even during normal operation.
# Investigate new differences or roll back as necessary.
# Verify the application and served certificate on actual TLS endpoints.
# Reboot completion alone does not establish application health.
# Record results in the CR. Complete verification before selecting another host.
```

### Field: Test Plan

```bash
# Compare the endpoint status before and after the change to make sure
# they are the same. If they are not the same, investigate or roll back.
#
# activate_cert.yml performs endpoint testing at the beginning and end;
# test.yml does not need to be executed separately during activation.
#
# Tomcat endpoints are derived from installed WAR files. Some vendors do
# not follow the expected naming conventions, so some generated URLs may
# be invalid even when the server is functioning normally.
#
# Consistent before-and-after results are a workable indication that
# Tomcat came back up and the certificate installation likely succeeded.
# Also verify application availability and the served certificate on each
# actual TLS endpoint. Reboot completion alone is not acceptance.
# Record results and any investigation or recovery actions in the CR.
```

### Field: Roll Back Plan

```bash
# ROLLBACK PLAN AND EMERGENCY RECOVERY
# Execute interactively, one step at a time. Stop on unexpected results.
# Validate the deployed rollback playbook and interface on a development
# host before production use.
#
# rollback_cert.yml defaults to report-only mode.
# Apply requires: -e cert_rollback_apply=true.
# Rollback points current directly to the directory resolved by rollback.
# It does not modify rollback or point current at the rollback symlink.
# Example after recovery:
#   current  -> /etc/pki/java/2026
#   rollback -> /etc/pki/java/2026
#
# Normal rollback requires no TDX download, ZIP identification, or certificate
# installation. The previous generation must already be present.
# Do not run activation apply as a recovery check: it may reactivate the
# failed newer generation.

# 0. ACCESS THE PLAYBOOKS ON ANSIBLE-AS
# All playbooks reside in /home/ansiblecontrol/sjf-ansible/cert.
# Run subsequent commands in the shell opened by each preceding login step.
ssh ansible-as
sudo su - ansiblecontrol
cd sjf-ansible/cert

# Set the personal SSH userid of the person performing recovery.
export operator='<your-userid>'
printf 'Ansible SSH userid: %s\n' "$operator"

# 1. SELECT ONLY THE HOST REQUIRING RECOVERY
# Retain the trailing comma. Recover and verify one host at a time.
# Do not blindly roll back all hosts in a partially completed rollout.
# An untouched host may have a rollback link from an older change.
# If the host is unreachable, arrange console or recovery access.
export target='<target>,'
printf 'Rollback inventory: %s\n' "$target"
ansible -i "${target:?Set target first}" all --list-hosts

# 2. INSPECT AND CONFIRM THE RECOVERY GENERATION
ansible -i "${target:?Set target first}" all -u "${operator:?Set operator first}" -k -K -b -m ansible.builtin.command -a 'readlink -f /etc/pki/java/current'
ansible -i "${target:?Set target first}" all -u "${operator:?Set operator first}" -k -K -b -m ansible.builtin.command -a 'readlink -f /etc/pki/java/rollback'

# Compare rollback with this host's pre-change current generation recorded
# in the CR. Stop if it is wrong, missing, or inconsistent.
# Preserve both generations. A resolved pathname alone does not establish
# that its certificate material is complete and suitable for recovery.

# 3. PREVIEW ROLLBACK
# Review the intended recovery target and resolve blockers before applying.
ansible-playbook -i "${target:?Set target first}" rollback_cert.yml -u "${operator:?Set operator first}" -k -K

# 4. APPLY ROLLBACK AND REBOOT AS NEEDED
# Atomically changes current, leaves rollback unchanged, and performs
# configuration checks. Transaction progress is recorded in:
# /etc/pki/java/.rollback-state.json
#
# Apache validation uses apachectl configtest. Tomcat checks are limited
# to XML parsing and certain configured keystore paths; they do not prove
# keystore passwords, full Tomcat validity, or application health.
#
# If post-switch validation fails, the playbook attempts to restore the
# pre-attempt current link and stops without rebooting. Restoration is not
# guaranteed; a restoration failure requires manual recovery.
ansible-playbook -i "${target:?Set target first}" rollback_cert.yml -u "${operator:?Set operator first}" -k -K -e cert_rollback_apply=true

# 5. VERIFY RECOVERY
ansible -i "${target:?Set target first}" all -u "${operator:?Set operator first}" -k -K -b -m ansible.builtin.command -a 'readlink -f /etc/pki/java/current'
ansible -i "${target:?Set target first}" all -u "${operator:?Set operator first}" -k -K -b -m ansible.builtin.command -a 'readlink -f /etc/pki/java/rollback'

# Both links should resolve to the intended previous generation.
# Check application availability and served certificates on actual TLS
# endpoints. Reboot completion alone is not acceptance.
# Use the standalone diagnostic if helpful, and compare with the baseline.
ansible-playbook -i "${target:?Set target first}" test.yml -u "${operator:?Set operator first}" -k -K

# 6. VERIFY REPEAT-RUN BEHAVIOR
# Preview again. After completed recovery, expect no switch and no reboot.
ansible-playbook -i "${target:?Set target first}" rollback_cert.yml -u "${operator:?Set operator first}" -k -K

# DEVELOPMENT ACCEPTANCE TESTING ONLY:
# Repeat apply on a development host to confirm no link change or reboot
# after completed recovery. Do not run this solely as a production check.
# If an earlier apply switched current but did not complete the reboot,
# transaction state can cause repeated apply to finish the pending reboot.
# It must not toggle certificate generations.
# The following is a development-only command, not a routine production step.
ansible-playbook -i "${target:?Set target first}" rollback_cert.yml -u "${operator:?Set operator first}" -k -K -e cert_rollback_apply=true

# 7. CLOSE OUT
# Record results, generation paths, certificate evidence, and remaining
# issues in the change record and associated TDX ticket as appropriate.
# Retain failed/new material, both generations, and diagnostics.
# Do not remove transaction state or either generation without understanding
# its role. Do not use activation apply as a recovery verification step.
```

## 6. Standalone Utilities

### `test.yml` — Endpoint and certificate checks

Discovers Tomcat endpoints based on installed WAR files and tests the derived URLs. Vendor naming conventions can make some derived URLs invalid; this is not a foolproof application-health test.

Comparing the same results before and after a certificate change provides a workable indication that Tomcat came back up. Consistent results make a successful installation very likely, but do not replace verification of the actual application and served certificate.

Its testing functionality is integrated into the beginning and end of `activate_cert.yml`, so running it separately during activation is unnecessary.

```bash
ansible-playbook -i "${target:?Set target first}" test.yml -u "${operator:?Set operator first}" -k -K
```

### `reboot.yml` — Standalone reboot

Reboots the selected target independently of the certificate workflow. Run only when an outage is authorized.

```bash
ansible-playbook -i "${target:?Set target first}" reboot.yml -u "${operator:?Set operator first}" -k -K
```

