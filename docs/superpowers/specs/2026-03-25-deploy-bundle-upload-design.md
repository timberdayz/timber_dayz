# Deploy Bundle Upload Design

**Date:** 2026-03-25  
**Last Updated:** 2026-03-25

## Goal

Make GitHub Actions production deployment more reliable for a domestic cloud server by replacing repeated small-file SCP uploads with a single deployment bundle upload.

## Problem

The current workflow can successfully establish SSH and upload some files, then later fail on additional `ssh/scp` calls with timeouts. This points to unstable cross-border SSH connectivity being amplified by too many separate upload operations.

## Decision

Switch the workflow sync step from:

- multiple `scp` uploads for compose/config/sql/nginx files

to:

- build one `deploy_bundle.tgz`
- upload the bundle once
- extract it on the server in one SSH step

## Scope

In scope:

- `.github/workflows/deploy-production.yml`
- a new helper script to build the bundle
- deployment pipeline tests

Out of scope:

- changing the image build/push process
- changing the remote deploy script contract
- changing release tagging semantics

## Expected Result

- fewer SSH/SCP round trips
- lower sensitivity to transient network loss
- same deployed file set as before, minus legacy metabase config sync
