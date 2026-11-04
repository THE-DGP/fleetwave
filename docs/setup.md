# Setup (Windows 11 / PowerShell)

Run every command from `D:\hustle\FleetWave` unless stated. Replace `<github-user>` and `<org>`.

## 1. Install missing tools

You already have Python 3.11, Docker Desktop (includes `kubectl`) and WSL.

```powershell
winget install --id Git.Git -e
winget install --id Kubernetes.kind -e
winget install --id Helm.Helm -e
winget install --id Microsoft.AzureCLI -e
```

**pluto** (needed from Phase 4). Try `winget search pluto` first. If FairwindsOps Pluto is not listed:

1. Download `pluto_<version>_windows_amd64.tar.gz` from https://github.com/FairwindsOps/pluto/releases
2. Then:
   ```powershell
   mkdir C:\tools -Force
   tar -xzf $HOME\Downloads\pluto_*_windows_amd64.tar.gz -C C:\tools
   [Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\tools", "User")
   ```

**Docker Desktop:** Settings > General > tick **Use the WSL 2 based engine**. Docker must be running for kind.

Close and reopen PowerShell, then check (paste the output back to me):

```powershell
git --version; kind version; helm version --short; az --version | Select-Object -First 1; pluto version; docker version --format '{{.Server.Version}}'
```

## 2. Python environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
pip install -e ".[dev]"
ruff check .
pytest
fleetwave version
```

## 3. First commit

```powershell
git config --global user.name "Dev Patel"
git config --global user.email "<your email>"
git init -b main
git add .
git commit -m "Phase 0: repo skeleton, tooling, CI and backlog"
```

## 4. GitHub

1. Go to https://github.com/new and name the repo `fleetwave`. Make it Public, and **do not** add a README, .gitignore or licence.
2. Then:
   ```powershell
   git remote add origin https://github.com/<github-user>/fleetwave.git
   git push -u origin main          # Git Credential Manager opens a browser to sign in
   ```

## 5. Azure DevOps organisation, project and Azure Repos

1. Go to https://dev.azure.com, sign in with a Microsoft account (your personal email is fine) and choose **Create new organization**. Pick a name like `devpatel-fleetwave` and the region **Europe** or **UK**.
2. Choose **New project** and name it `FleetWave`. Visibility can be **Private** (or Public).
   Under **Advanced**, set Version control = **Git** and Work item process = **Agile**. You need Agile to get Epic, Feature and User Story.
3. Open **Repos > Files** and copy the clone URL. Then send each `git push` to both GitHub and Azure:
   ```powershell
   git remote set-url --add --push origin https://github.com/<github-user>/fleetwave.git
   git remote set-url --add --push origin https://<org>@dev.azure.com/<org>/FleetWave/_git/FleetWave
   git push origin main
   git remote -v          # shows 1 fetch URL and 2 push URLs
   ```
   You must add both push URLs. Once you add any push URL, git stops using the original URL for pushes.

## 6. Azure Boards backlog

1. Go to **Project settings > Boards > Team configuration > Backlog navigation levels** and tick **Epics**.
2. Go to **Boards > Work items > Import Work Items**, choose `docs\backlog.csv`, click **Import**, then **Save items**.
   The `Title 1/2/3` columns create the Epic > Feature > User Story hierarchy automatically.
3. Check it under **Boards > Backlogs > Epics**, which should show 3 Epics, 7 Features and 18 User Stories. Move the 2 Phase 0 stories to Done once steps 1–7 are finished.
   If the import errors, create the items by hand from `docs/backlog.md`.

## 7. Pipeline capacity (Microsoft-hosted, free)

New organisations get **0** hosted parallel jobs until Microsoft grants the free tier.

1. Request the grant at https://aka.ms/azpipelines-parallelism-request with your org name and project visibility. It usually takes 2–3 business days.
   Check progress in **Organization settings > Pipelines > Parallel jobs**.
2. Create the pipeline now so it's ready: **Pipelines > New pipeline > Azure Repos Git > FleetWave > Existing Azure Pipelines YAML file > `/azure-pipelines.yml` > Run**.
   Until the grant arrives, you'll see *"No hosted parallelism has been purchased or granted"*. That's expected.

### Fallback: self-hosted agent on your PC (works immediately)

1. Create a personal access token under **User settings (top right) > Personal access tokens > New token**, with scope **Agent Pools: Read & manage**. Copy it.
2. Go to **Organization settings > Agent pools > Default > New agent > Windows > Download**. Then:
   ```powershell
   mkdir C:\agents\fw -Force; cd C:\agents\fw
   Expand-Archive $HOME\Downloads\vsts-agent-win-x64-*.zip -DestinationPath .
   .\config.cmd      # URL: https://dev.azure.com/<org> | auth: PAT | pool: Default | run as service: N
   .\run.cmd         # leave this window open while pipelines run
   ```
3. In `azure-pipelines.yml`, change `vmImage: ubuntu-latest` to `name: Default` and delete the two
   `UsePythonVersion@0` steps. The agent then uses your installed Python 3.11.

## Done criteria for Phase 0

- [ ] `pytest` passes locally
- [ ] repo visible on GitHub and in Azure Repos
- [ ] backlog imported
- [ ] grant requested (or self-hosted agent online) and pipeline run green
