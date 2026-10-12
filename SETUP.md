# Local setup

These steps get a machine to the point where this command works:

```bash
python -m middleware.pipeline data/synthetic/hermes_pointcloud_10s.json \
  --origin scenarios/campus_origin.json \
  --publish
```

That command reads a synthetic track file, writes `build/normalized_tracks.json`, and PUTs the tracks to a local InterUSS mock. The mock has to be running first. The pipeline uses the Python standard library only, so there is no `pip install` for this command.

Two checkouts are involved:

- This repo, which holds the pipeline.
- [interuss/monitoring](https://github.com/interuss/monitoring), which holds the local sandbox (`mock_uss`, the DSS, and the dummy OAuth server). Leave that clone outside this repo.

## 1. Install the tools

On Windows:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Git
- Python 3.10 or newer (`python --version`). 3.12 is what this was run with.

Docker Desktop needs the WSL 2 backend. In **Settings → General**, leave **Use the WSL 2 based engine** on.

## 2. Install Ubuntu

From an **Administrator** PowerShell window:

```powershell
wsl --install -d Ubuntu
wsl --set-default Ubuntu
```

Open **Ubuntu** from the Start menu and finish the first-time username prompt. The `wsl` command itself only exists in Windows PowerShell. Once the prompt says `username@computer`, you are already inside Ubuntu.

In Docker Desktop, open **Settings → Resources → WSL integration** and turn Ubuntu on. Apply and restart if Docker asks.

## 3. Let Ubuntu talk to Docker

In the Ubuntu terminal:

```bash
sudo usermod -aG docker $USER
```

Close the Ubuntu window completely, open a new one, and check:

```bash
docker ps
```

An empty table is fine. `permission denied` on `/var/run/docker.sock` means the new shell was opened before the group change, or WSL integration is still off.

Ubuntu also needs Make and Git:

```bash
sudo apt update
sudo apt install -y make git
```

## 4. Start the sandbox

In Ubuntu:

```bash
mkdir -p ~/src
cd ~/src
git clone https://github.com/interuss/monitoring.git
cd monitoring
make start-locally
COMPOSE_PROFILES=rid make start-uss-mocks
```

`make start-locally` starts the dummy OAuth server, the DSS, and CockroachDB. The second command starts the Remote ID mocks, which is the service this pipeline publishes into. The first run downloads images and can take several minutes. Later starts are usually under two minutes.

When the prompt returns, check the containers:

```bash
docker container ls
```

These need to be **Up** and **healthy** before the pipeline can publish:

| Container | Port on localhost | Used for |
|---|---|---|
| dummy OAuth | 8085 | Access token |
| mock Service Provider (`ridsp`) | 8081 | Track injection |
| DSS and CockroachDB | — | Area registration behind the mock |

The display mock on port 8083 can be up too. This publish command does not call it. A restarting `mock_uss_tls_proxy` does not block the publish.

From Windows PowerShell, this should return `200`:

```powershell
(Invoke-WebRequest -Uri "http://localhost:8085/token?grant_type=client_credentials&intended_audience=localhost&scope=rid.inject_test_data" -UseBasicParsing).StatusCode
```

Docker Desktop publishes those ports onto Windows `localhost`, so the pipeline can run in PowerShell while the containers run in Ubuntu.

## 5. Run the pipeline

Clone this repo if you do not already have it, then from the repo root in PowerShell:

```powershell
git clone https://github.com/AdamWalters1/SeniorDesignRepo.git
cd SeniorDesignRepo
python -m middleware.pipeline data/synthetic/hermes_pointcloud_10s.json --origin scenarios/campus_origin.json --publish
```

Success looks like:

```text
Wrote 33 points to build/normalized_tracks.json
Published test pipeline-xxxxxxxx (3 flights)
```

The same command works inside Ubuntu with `python3` if the repo is on the Windows drive, for example under `/mnt/c/Users/.../SeniorDesignRepo`.

Each run makes a new test id. Passing `--test-id` with an id that was already injected can be rejected. Sample times are moved so the first point starts two minutes ahead of the current clock, because the DSS rejects a start time in the past.

The radar sample uses the same sandbox:

```powershell
python -m middleware.pipeline data/hermespy/radar_fmcw_11s.json --format radar --origin scenarios/campus_origin.json --publish
```

## 6. Tests without the sandbox

Unit tests do not need Docker:

```powershell
python -m unittest discover -s tests
```

## Stop the sandbox

From `~/src/monitoring` in Ubuntu:

```bash
make stop-uss-mocks
make down-locally
```

## If image pulls fail

`docker pull` ending in `EOF` from `production.cloudfront.docker.com`, including for `hello-world`, was fixed by turning off a Docker Desktop setting:

**Settings → General → Use containerd for pulling and storing images** → off, then **Apply & restart**.

If `make start-locally` times out near four minutes while images are still downloading, run it again after the pulls finish.
