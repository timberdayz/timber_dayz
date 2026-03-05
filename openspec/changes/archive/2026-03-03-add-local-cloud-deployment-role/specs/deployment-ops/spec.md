## ADDED Requirements

### Requirement: Local and cloud deployments SHALL be distinguished by configuration and optional Docker image variant
The system SHALL support two deployment roles from the same codebase: **local** (collection, data sync, and local-to-cloud sync) and **cloud** (system operation only: dashboards, reports, API). The role SHALL be determined at runtime by configuration (e.g. `ENABLE_COLLECTION` or `DEPLOYMENT_ROLE`). When an image registry is used, the build SHALL support an optional variant that includes Playwright and browser dependencies for the local role; the cloud deployment SHALL use an image built without Playwright.

#### Scenario: Cloud deployment does not start collection scheduler
- **WHEN** the application starts with `ENABLE_COLLECTION=false` (or `DEPLOYMENT_ROLE=cloud`)
- **THEN** the collection scheduler SHALL NOT be created or started
- **AND** the application SHALL remain healthy and serve API and dashboards from the cloud database

#### Scenario: Local deployment starts collection scheduler
- **WHEN** the application starts with `ENABLE_COLLECTION=true` (or `DEPLOYMENT_ROLE=local`)
- **THEN** the collection scheduler MAY be created and started according to existing schedule configuration
- **AND** the same codebase SHALL be used as for cloud deployment

#### Scenario: Docker build argument controls Playwright installation
- **WHEN** the production Docker image is built with `--build-arg INSTALL_PLAYWRIGHT=false` (or omitted)
- **THEN** Playwright and browser dependencies SHALL NOT be installed in the image
- **AND** this image SHALL be suitable for cloud deployment

#### Scenario: Full image variant includes Playwright for local deployment
- **WHEN** the production Docker image is built with `--build-arg INSTALL_PLAYWRIGHT=true`
- **THEN** Playwright and required browser dependencies (e.g. Chromium) SHALL be installed in the image
- **AND** this image SHALL be suitable for the local (collection) deployment

#### Scenario: Deployment and daily operation flows are documented
- **WHEN** a maintainer or operator follows the deployment documentation
- **THEN** the documentation SHALL describe: (1) how to release a version (tag, push, CI building two images), (2) cloud deployment steps (pull default image, set ENABLE_COLLECTION=false, start), (3) local deployment steps (pull -full image, set ENABLE_COLLECTION=true and CLOUD_DATABASE_URL, configure Cron for local-to-cloud sync, start), (4) daily operation flow (four time slots for collection and data sync, staggered local-to-cloud sync, cloud read-only)
