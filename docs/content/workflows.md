# Reproducible Workflows with Snakemake & FDO (Conda-Based)

This document outlines the two main processes---**Creation** and
**Execution**---for using Snakemake workflows as Fair Digital Objects
(FDOs) managed by a DoIP server. This strategy relies on the **Conda**
environment management system to ensure reproducibility across
**Windows**, **Linux**, and **macOS** environments without needing
Docker or operating system compatibility layers.

---

## 1. Target System Preparation (User Role)

The User must prepare their local operating system (Windows, Linux, or
macOS) by installing the core components necessary to run the
Conda-based Snakemake workflow. This setup is required once per machine.

=== "Windows"

    The Windows user needs four essential pieces of software installed:

    1. **Mamba/Conda:** Install **Miniforge** (recommended):
        - Download from [conda-forge.github.io/miniforge](https://conda-forge.github.io/miniforge)
        - Run the `.exe` installer and select "Add to PATH" during installation
        - Verify: Open PowerShell or CMD and run `mamba --version`

    2. **Python:** Comes bundled with Miniforge (Python 3.9+ recommended).
        - Verify: `python --version`

    3. **Snakemake:** Install the Snakemake engine:

        ```powershell
        mamba install -c conda-forge -c bioconda snakemake
        ```

    4. **FDO Client:** Install your custom command-line client:
        - Download the latest `fdo-client-windows-x64.exe` CLI from [https://github.com/MaRDI4NFDI/mardi_doip_server]
        - Rename to `fdo-run-client.exe` and move to a directory in your PATH (e.g., `C:\Tools\`)
        - Verify: `fdo-run-client --version`

=== "Linux"

    The Linux user needs four essential pieces of software installed:

    1. **Mamba/Conda:** Install **Miniforge** (recommended):
        ```bash
        wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
        bash Miniforge3-Linux-x86_64.sh
        # Follow prompts, then reload shell: source ~/.bashrc
        ```
        - Verify: `mamba --version`

    2. **Python:** Comes bundled with Miniforge (Python 3.9+ recommended).
        - Verify: `python --version`

    3. **Snakemake:** Install the Snakemake engine:

        ```bash
        mamba install -c conda-forge -c bioconda snakemake
        ```

    4. **FDO Client:** Install your custom command-line client:
        ```bash
        wget https://your-repo.internal/fdo-client-linux-x64 -O fdo-run-client
        chmod +x fdo-run-client
        sudo mv fdo-run-client /usr/local/bin/
        ```
        - Verify: `fdo-run-client --version`

=== "macOS"

    The macOS user needs four essential pieces of software installed:

    1. **Mamba/Conda:** Install **Miniforge** (recommended):
        - For Intel Macs: Download `Miniforge3-MacOSX-x86_64.sh`
        - For Apple Silicon (M1/M2/M3): Download `Miniforge3-MacOSX-arm64.sh`
        - Both available at [conda-forge.github.io/miniforge](https://conda-forge.github.io/miniforge)
        - Run: `bash Miniforge3-MacOSX-*.sh` and follow prompts
        - Reload shell: `source ~/.zshrc` (or `~/.bash_profile` for older macOS)
        - Verify: `mamba --version`

    2. **Python:** Comes bundled with Miniforge (Python 3.9+ recommended).
        - Verify: `python --version`

    3. **Snakemake:** Install the Snakemake engine:

        ```bash
        mamba install -c conda-forge -c bioconda snakemake
        ```

    4. **FDO Client:** Install your custom command-line client:
        ```bash
        # For Intel Macs
        curl -L https://your-repo.internal/fdo-client-macos-x64 -o fdo-run-client

        # For Apple Silicon (M1/M2/M3)
        curl -L https://your-repo.internal/fdo-client-macos-arm64 -o fdo-run-client

        chmod +x fdo-run-client
        sudo mv fdo-run-client /usr/local/bin/
        ```
        - Verify: `fdo-run-client --version`

---

## 2. Workflow Creation and FDO Registration (Creator Role)

The Creator develops a workflow designed for maximum portability and
registers the complete package as a persistent FDO artifact.

### 2.1 Develop the Snakemake Pipeline

The workflow must explicitly use the Snakemake **Conda integration** to
ensure cross-platform reproducibility.

1.  **Write the Snakefile:** Define the logic, rules, inputs, and
    outputs of your pipeline.

2.  **Define Isolated Environments:** For every external tool or
    dependency, create a dedicated **`environment.yaml`** file listing
    version-locked dependencies (e.g., `fastqc=0.11.9`, `python=3.9`).

3.  **Link Environments in the Snakefile:** Ensure every rule points to
    its environment file using the `conda:` directive.

Example Snakefile snippet:

```python
rule fastqc_report:
    input:
        "data/{sample}.fastq"
    output:
        "results/{sample}_fastqc.html"
    conda:
        "envs/fastqc.yaml"
    shell:
        "fastqc {input} -o {output}"
```

4.  **Test for Portability:** Test the workflow on Windows, Linux, and
    macOS using the `--use-conda` flag to confirm environments build
    correctly and execution is identical across systems.

### 2.2 Package and Register the FDO

The validated workflow files are packaged as a Research Object Crate
(RO-Crate) and registered in the DoIP/FDO system.

1.  **Bundle Artifacts (RO-Crate):** Package the `Snakefile`, all
    `environment.yaml` files, configuration files, and a `README` into a
    single archive (ZIP or TAR).
2.  **Calculate Checksum:** Generate a cryptographic hash (e.g.,
    SHA-256) of the final RO-Crate archive.
3.  **Store and Mint PID:**
    -   Upload the RO-Crate to durable storage.
    -   The automated registration service calls the **DoIP server** to
        mint a new **PID** whose resolution record stores the storage
        URL and checksum.
4.  **Register FDO:** Submit the complete FDO metadata (PID, creator,
    description, parameters, checksum, dependency list) to the **FDO
    Registry**.

---

## 3. Workflow Execution (User Role)

The User executes the verified workflow on their local machine using the
PID and local Conda installation.

### 3.1 Execute the FDO Client

The FDO client automates the download, verification, and Snakemake
execution steps.

1.  **Initiate Run:** Execute the workflow using its PID and specify the
    local input directory.

    ```bash
    fdo-run-client 20.500.12345/workflow_A01 --input "C:\User\Data\RawSequences" --cores 4
    ```

2.  **Client Verification Logic:**

    The client performs the following verifiable steps programmatically:

    -   **Resolve PID:** Query the DoIP server to retrieve the storage
        URL and original checksum.
    -   **Download & Extract:** Download the RO-Crate and extract it to
        a temporary working directory.
    -   **Verify Integrity:** Calculate the checksum of the downloaded
        archive. Execution stops if it does not match the PID record.
    -   **Prepare:** Map the user input directory into the Snakemake
        configuration.

3.  **Snakemake Execution:** The client launches the Snakemake run
    command:

    ```bash
    snakemake -s /path/to/Snakefile --cores 4 --use-conda --conda-frontend mamba --config input_path="/path/to/input/data"
    ```

### 3.2 Guaranteed Reproducibility Across OS

Because the `--use-conda` flag is used:

-   **Snakemake** reads the `environment.yaml` files from the downloaded
    RO-Crate.
-   **Mamba** creates isolated environments with exact dependency
    versions compiled for the user's OS.
-   The workflow runs identically across Windows, Linux, and macOS
    without requiring Docker or virtualization.

---

## Example

See [this example](workflow_example.md).

---

## Appendix: Conda Distributions Compared

**Conda** is the underlying package manager and environment system; the others are distributions that bundle it. **Anaconda** is the original full distribution---it ships with hundreds of pre-installed scientific packages but is large (~3 GB), slow to install, and its default channel carries a commercial licensing restriction for organisations above a certain size. **Miniconda** is Anaconda's minimal counterpart---just Conda and Python, no pre-installed packages---which is lighter but still defaults to the `defaults` channel and inherits the same licensing ambiguity. **Miniforge** is the recommended choice here: it is equally minimal but defaults to the community-maintained **conda-forge** channel, ships with **Mamba** (a significantly faster dependency resolver) out of the box, and carries no licensing restrictions. For scientific workflows on conda-forge, Miniforge is the cleanest starting point on all three platforms.

| Distribution | Size | Default Channel | Includes Mamba | License |
|---|---|---|---|---|
| **Miniforge** ✓ | Minimal | conda-forge | Yes | No restrictions |
| Miniconda | Minimal | defaults | No | Anaconda ToS |
| Anaconda | ~3 GB | defaults | No | Commercial restrictions |