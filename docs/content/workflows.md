# Reproducible Workflows with Snakemake & FDO (Conda-Based)

This document outlines the two main processes---**Creation** and
**Execution**---for using Snakemake workflows as Fair Digital Objects
(FDOs) managed by a DoIP server. This strategy relies on the **Conda**
environment management system to ensure reproducibility across
**Windows**, **Linux**, and **macOS** environments without needing
Docker or operating system compatibility layers.

------------------------------------------------------------------------

## 1. Target System Preparation (User Role)

The User must prepare their local operating system (Windows, Linux, or
macOS) by installing the core components necessary to run the
Conda-based Snakemake workflow. This setup is required once per machine.

=== "Windows"

    The Windows user needs four essential pieces of software installed:

    1. **Conda/Mamba:** Install **Anaconda** or **Miniconda** (preferred for a smaller footprint).
    2. **Python:** Ensure Python is installed (usually comes with Conda).
    3. **Snakemake:** Install the Snakemake engine:

        ```bash
        conda install -c conda-forge snakemake
        ```

    4. **FDO Client:** Install your custom command-line client for resolving PIDs and running the workflow.

=== "Linux"

    The Linux user needs four essential pieces of software installed:

    1. **Conda/Mamba:** Install **Anaconda** or **Miniconda** (preferred for a smaller footprint).
    2. **Python:** Ensure Python is installed (usually comes with Conda).
    3. **Snakemake:** Install the Snakemake engine:

        ```bash
        conda install -c conda-forge snakemake
        ```

    4. **FDO Client:** Install your custom command-line client for resolving PIDs and running the workflow.

=== "macOS"

    The User needs four essential pieces of software installed:

    1. **Conda/Mamba:** Install **Anaconda** or **Miniconda** (preferred for a smaller footprint).
    2. **Python:** Ensure Python is installed (usually comes with Conda).
    3. **Snakemake:** Install the Snakemake engine:

        ```bash
        conda install -c conda-forge snakemake
        ```

    4. **FDO Client:** Install your custom command-line client for resolving PIDs and running the workflow.

------------------------------------------------------------------------

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

``` python
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

------------------------------------------------------------------------

## 3. Workflow Execution (User Role)

The User executes the verified workflow on their local machine using the
PID and local Conda installation.

### 3.1 Execute the FDO Client

The FDO client automates the download, verification, and Snakemake
execution steps.

1.  **Initiate Run:** Execute the workflow using its PID and specify the
    local input directory.

    ``` bash
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

    ``` bash
    snakemake -s /path/to/Snakefile --cores 4 --use-conda --config input_path="/path/to/input/data"
    ```

### 3.2 Guaranteed Reproducibility Across OS

Because the `--use-conda` flag is used:

-   **Snakemake** reads the `environment.yaml` files from the downloaded
    RO-Crate.
-   **Conda** creates isolated environments with exact dependency
    versions compiled for the user's OS.
-   The workflow runs identically across Windows, Linux, and macOS
    without requiring Docker or virtualization.

------------------------------------------------------------------------

## Example

See [this example](workflow_example.md).
