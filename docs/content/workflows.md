## Reproducible Workflows with Snakemake & FDO (Conda-Based)

This document outlines the two main processes—**Creation** and **Execution**—for using Snakemake workflows as Fair Digital Objects (FDOs) managed by a DoIP server. This strategy relies on the **Conda** environment management system to ensure reproducibility across **Windows**, **Linux**, and **macOS** environments without needing Docker or operating system compatibility layers.

---

## 1. Target System Preparation (User Role)

The User must prepare their local operating system (Windows, Linux, or macOS) by installing the core components necessary to run the Conda-based Snakemake workflow. This setup is required once per machine.

### Step 1: Prepare the Windows Environment

The User needs four essential pieces of software installed:

1.  **Conda/Mamba:** Install **Anaconda** or **Miniconda** (preferred for a smaller footprint).
2.  **Python:** Ensure Python is installed (usually comes with Conda).
3.  **Snakemake:** Install the Snakemake engine:
    ```bash
    conda install -c conda-forge snakemake
    ```
4.  **FDO Client:** Install your custom command-line client for resolving PIDs and running the workflow.

### Step 2: Prepare the Linux Environment

The User needs four essential pieces of software installed:

1.  **Conda/Mamba:** Install **Anaconda** or **Miniconda** (preferred for a smaller footprint).
2.  **Python:** Ensure Python is installed (usually comes with Conda).
3.  **Snakemake:** Install the Snakemake engine:
    ```bash
    conda install -c conda-forge snakemake
    ```
4.  **FDO Client:** Install your custom command-line client for resolving PIDs and running the workflow.

### Step 3: Prepare the macOS Environment

The User needs four essential pieces of software installed:

1.  **Conda/Mamba:** Install **Anaconda** or **Miniconda** (preferred for a smaller footprint).
2.  **Python:** Ensure Python is installed (usually comes with Conda).
3.  **Snakemake:** Install the Snakemake engine:
    ```bash
    conda install -c conda-forge snakemake
    ```
4.  **FDO Client:** Install your custom command-line client for resolving PIDs and running the workflow.

---

## 2. Workflow Creation and FDO Registration (Creator Role) 

The Creator develops a workflow designed for maximum portability and registers the complete package as a persistent FDO artifact. 

### 2.1. Develop the Snakemake Pipeline

The workflow must explicitly use the Snakemake **Conda integration** to ensure cross-platform reproducibility.

1.  **Write the Snakefile:** Define the logic, rules, inputs, and outputs of your pipeline.

2.  **Define Isolated Environments:** For every external tool or dependency, create a dedicated **`environment.yaml`** file. These files are crucial as they precisely list the version-locked dependencies (e.g., `fastqc=0.11.9`, `python=3.9`).

3.  **Link Environments in the Snakefile:** Ensure every rule points directly to its environment file using the `conda:` directive.

    > Example Snakefile Snippet:
    > ```python
    > rule fastqc_report:
    >     input:
    >         "data/{sample}.fastq"
    >     output:
    >         "results/{sample}_fastqc.html"
    >     conda:
    >         "envs/fastqc.yaml" # Links to the environment definition
    >     shell:
    >         "fastqc {input} -o {output}"
    > ```

4.  **Test for Portability:** Test the workflow on various operating systems (Windows, Linux, macOS) using the `--use-conda` flag to confirm that the environment files successfully build and the workflow executes identically across platforms.

### 2.2. Package and Register the FDO

The validated workflow files are packaged as a Research Object Crate (RO-Crate) and registered to the DoIP/FDO system.

1.  **Bundle Artifacts (RO-Crate):** Package the `Snakefile`, all `environment.yaml` files, configuration files, and a `README` into a single RO-Crate archive (e.g., a ZIP or TAR archive).
2.  **Calculate Checksum:** Generate a cryptographic hash (e.g., SHA-256) of the final RO-Crate archive.
3.  **Store and Mint PID:**
    * Upload the RO-Crate to the durable storage system.
    * The automated registration service calls the **DoIP server** to mint a new **PID**. The PID's resolution data must store the storage URL and the **Checksum**.
4.  **Register FDO:** Submit the complete FDO metadata (PID, creator, description, input parameters, **checksum**, and dependency list) to the **FDO Registry**.

---

## 3. Workflow Execution (User Role)

The User executes the verified, reproducible workflow on their local machine using the PID and local Conda installation. 

### 3.1. Execute the FDO Client

The FDO client automates the download, verification, and Snakemake execution steps.

1.  **Initiate Run:** The User executes the workflow using its PID and specifies the local input data directory.

    > Example Command (Windows):
    > ```bash
    > fdo-run-client 20.500.12345/workflow_A01 --input "C:\User\Data\RawSequences" --cores 4
    > ```

2.  **Client Verification Logic:**

    The client handles the critical, verifiable steps programmatically:
    * **Resolve PID:** Queries the DoIP server to retrieve the Storage URL and the original Checksum.
    * **Download & Extract:** Downloads the RO-Crate and extracts it to a temporary working directory.
    * **Verify Integrity:** Calculates the checksum of the downloaded file. **Execution stops if this value does not match the PID's original checksum.**
    * **Prepare:** Maps the user's input directory into the Snakemake configuration.

3.  **Snakemake Execution:** The client initiates the Snakemake run command:

    ```bash
    snakemake -s /path/to/Snakefile --cores 4 --use-conda --config input_path="/path/to/input/data"
    ```

### 3.2. Guaranteed Reproducibility Across OS

Because the `--use-conda` flag is employed:

* **Snakemake** reads the `environment.yaml` files within the downloaded RO-Crate.
* **Conda** automatically creates temporary, isolated software environments with the exact, version-locked dependencies compiled for the **User's specific OS** (Windows, Linux, or macOS).
* The workflow runs identically across all supported platforms, achieving high-fidelity reproducibility without external virtualization layers.