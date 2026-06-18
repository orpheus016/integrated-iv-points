# copilot-instructions.md

## 1. System Architecture Principles

* **Single Responsibility Principle (SRP):** Every module must have exactly one reason to change.
* data_source/ handles raw data ingestion and I/O. (includes serial_commander.py for sending serial commands to the hardware, ads1256.py for hardware streaming, and csv_replay.py for testbench replay)
* backbones/ handles data filtering, stability mathematics, and state tracking. (snapshot algorithms)
* software/config/config.py handles parameters and runtime flags. (arguments and configurations)
* main.py is the execution coordinator.


* **The Streaming Generator Pattern:** Data pipelines must use memory-efficient streaming.
* Data sources must yield samples one by one using yield.
* Backbones must process single samples via an incremental update method rather than consuming whole arrays.



---

## 2. Strict Implementation Rules

### Python Implementation Constraints

* **DO NOT** write raw strings or hardcoded numeric constants inside processing logic. All thresholds, command bytes (R, C, s), delay counts, and default paths must live in config.py or as explicit CLI parameters.
* **DO NOT** pass loose tuples or dictionary objects down the pipeline. Use the frozen Snapshot dataclass in software/utils/types.py to enforce type-safety and structural contracts across loggers, evaluators, and downstream applications.
* **DO** use explicit type hinting on all functions, classes, and generator signatures.
* **DO** use relative imports inside nested directories (e.g., from .base import BaseBackbone) to keep modules self-contained and portable.

### Hardware & Data Source Constraints

* **DO NOT** mix serial port execution, frame parsing, or hardware connection state into main.py or scripts/evaluate.py.
* **DO** isolate the serial protocol state engine into data_source/serial_commander.py.
* **DO** keep stream markers exact and explicit: `*STREAM_START` and `*STREAM_STOP` are the only legal framing markers for the Arduino stream.
* **DO** centralize current-switch thresholds in software/config/config.py and treat the switching policy as hardware-boundary logic, not backbone logic.
* **DO** enforce identical generator interfaces for both --ads1256 (hardware) and --testbench (CSV replay) and also --[data_source custom signal] so that changing modes requires zero code adjustments inside the core execution loop.
* **DO** route data_source output into output/[name] to keep hardware and testbench logs separate and easily identifiable. except on manual capture mode it will be sent to testbench output for easier evaluation and comparison.

### Backbones (IV Snapshot Algorithms)

* **DO NOT** load entire historical windows into memory or compute raw array standard deviations on every incoming frame. Use streaming/online algorithms (e.g., Welford’s algorithm for running variance) to keep memory footprint bounded.
* **DO** inherit all snapshot strategies from a unified abstract base class (backbones/base.py) that strictly enforces the update(self, sample: Tuple[float, float, float]) -> Optional[Snapshot] execution contract, where the sample is (timestamp, voltage, current_mA).
* **DO** isolate hysteresis windows and stable dwell counters completely inside the chosen backbone class.

### Config

* **DO** centralize all tunable parameters, thresholds, and CLI argument defaults in software/config/config.py. main.py should only read from config.py and never have hardcoded defaults or logic branching based on these flags.
* **DO** let the user be able to choose which backbone to evaluate, which data source to use, and which snapshot parameters to set via CLI arguments that override config.py defaults. also add flags to decide the data capture when to stop the data capture after snapshot or not, and whether to show continuous graph updates or just a final comparison after snapshot.

---

## 3. Script and Directory Mapping

### File Allocation Rules

* **software/main.py**: Operates exclusively as the real-time runtime orchestration layer. It instantiates the factory-selected data source and streams data directly to the chosen backbone and output logger.
* **software/scripts/evaluate.py**: A pure offline profiling script. It must not communicate with serial hardware. It must load static datasets, iterate through multiple backbone strategies simultaneously, and calculate error metrics to evaluate stability performance.
* **software/scripts/integrate.py**: Reserved as the programmatic API boundary. It defines how downstream toolchains import and interface with this software system as an external library without executing main.py.
* **software/scripts/ci_compliance.py**: Lightweight repository-shape check used by CI to enforce the architectural rules below.
* **software/scripts/README.md**: Developer guide for script entrypoints and usage examples.
* **software/utils/math.py**: utilities for mathematical operations especially inside backbones.
* **software/utils/filters.py**: utilities for filtering data.
* **software/utils/visualization.py**: utilities for visualizing data and results.
* **software/utils/logger.py**: utilities for logging data and results.
* **software/utils/csv_replay.py**: CSV replay generator for `voltage,current_mA` data.
* **software/utils/evaluate_helpers.py**: Evaluation helpers for offline evaluation and synthetic source construction.
* **software/utils/backbone_factory.py**: Shared backbone selection helper used by `main.py`, `scripts/evaluate.py`, and `scripts/integrate.py`.
* **software/utils/types.py**: Central data contracts (Snapshot and any shared type aliases).
* **software/output/ads1256**: CSV output from ADS1256.
* **software/output/dummy**: CSV output from dummy data source.
* **software/output/testbench**: CSV output from testbench simulations.
* **software/data_source/instrument_meas.py**: Serves as reference on how to read, parse, and communicate with ADS1256 via PySerial.
* **software/data_source/serial_commander.py**: Implementation for handling serial communication with the arduino.
* **software/data_source/ads1256.py**: Hardware streaming generator for ADS1256 with exact protocol markers and current switching.
* **software/data_source/dummy.py**: Dummny signal generator.
* **software/data_source/settling.py**: Artificial settling data source for backbone testing.
* **software/data_source/worst_case.py**: Simulation data source for worst-case scenarios especially on contact with oxide layer and N type doping of silicon wafer.
* **software/data_source/manual_capture.py**: Manual data capture utility for collecting custom datasets.
* **software/config/config.py**: Arguments and configuration settings.
* **software/backbones**: Folder containing snapshot algorithms.
* **CONTRIBUTING.md**: Root developer workflow guide for CI, tests, and PR expectations.

### I/O Boundaries

* **DO NOT** write output logs from hardware tests and simulation benchmarks to the same output path.
* **DO** enforce isolated outputs based on configuration flags:
* --ads1256 writes telemetry files to output/ads1256/
* --testbench writes telemetry files to output/testbench/
* --data_source write to output/[signal] for easy identification and separation of datasets. [DONT FORGET TO IMPLEMENT THIS]
* Use a per-run folder under the source output path (e.g., output/ads1256/volt_log_YYYYMMDD_HHMMSS/).
* Serial runs also save a combined transient PNG named `<csv_stem>_transient.png` next to the CSV.

### Arguments
* Add labels such as --ads1256, --testbench, --snapshot-mode, --plot-mode, and all snapshot parameters to config.py as default values. main.py should only read from config.py and never have hardcoded defaults or logic branching based on these flags.
* Current switching rules belong in config.py and must include the power limit, stage-specific raise thresholds, and the protocol timing used for stream restarts and marker waits.
* let the user be able to choose which backbone to evaluate, which data source to use, and which snapshot parameters to set via CLI arguments that override config.py defaults. also add flags to decide the data capture when to stop the data capture after snapshot or not, and whether to show continuous graph updates or just a final comparison after snapshot.
* let the user be able to decide the file name for the output csv file via CLI arguments that override config.py defaults.
* Include live plotting controls in config.py: `--live-plot`, `--plot-update-hz`, optional `--plot-backend`, and `--save-plot-on-interrupt`.
* Include live multi-backbone controls in config.py: `--live-backbones` (comma-separated) and `--live-duration` (seconds).

### Tests
* **DO** write comprehensive unit tests for all backbone implementations and data source modules, ensuring that they adhere to the defined interfaces and that their behavior is consistent with the architectural principles outlined in this document. preferable can be done using one script but plenty of arguments to specify which backbone, data source, and parameters to test.
* **DO** keep a small offline smoke test for `software/scripts/evaluate.py` that uses a bundled CSV dataset and verifies the evaluation outputs are written.
* **DO** keep the compliance checker in sync with this document whenever a file moves or a new public script/helper is added.

CI Checks:
* The repository includes a lightweight compliance script at `software/scripts/ci_compliance.py`.
* It performs AST-based checks to catch common architecture violations automatically:
    - duplicate top-level function names across `software/` modules (excludes `software/tests/` and `__init__.py`), and
    - uses of `add_argument` outside of `build_arg_parser` in `software/config/config.py`.
* Keep `ci_compliance.py` updated when moving public helpers or adding CLI flags.



---

## 4. Concrete Code Style Blueprint

```python
# Rule: Data contracts are frozen and structured
@dataclass(frozen=True)
class Snapshot:
    timestamp: float
    voltage: float
    current_mA: float
    resistance: Optional[float] = None
    std_dev: Optional[float] = None
    stage: Optional[str] = None

# Rule: All backbones inherit from a rigid interface
class BaseBackbone(ABC):
    @abstractmethod
    def update(self, sample: Tuple[float, float, float]) -> Optional[Snapshot]:
        """Processes (timestamp, voltage, current_mA) and returns a Snapshot if stable."""
        pass

# Rule: Clean, decoupled generator execution loop inside main.py
def run_pipeline(source: BaseDataSource, backbone: BaseBackbone, logger: DataLogger):
    source.initialize_session()
    try:
        for sample in source.read_samples():
            snapshot = backbone.update(sample)
            if snapshot:
                logger.write(snapshot)
                source.signal_next_stage()
    finally:
        source.close_session()

```



---

## 5. DOCUMENTATION AND MAINTENANCE

* **DO** maintain copilot-instructions.md as the single source of truth for architectural principles, implementation rules, and code style guidelines.
* **DO** update this document with any architectural changes, new backbone implementations, or adjustments to the data source interfaces.
* **DO** use this document as the primary reference for onboarding new contributors and for code reviews to ensure consistency and adherence to the defined architecture and style.
* **DO NOT** allow exceptions to the defined principles and rules without a documented rationale and a corresponding update to this instructions file.
* **DO** periodically review and refactor the codebase to ensure continued compliance with the architectural principles and implementation rules outlined in this document.
* **DO** use the examples and code snippets in this document as templates for new implementations and as references during development to maintain a consistent code style across the project.
* **DO NOT** introduce new dependencies or libraries without first evaluating their necessity and impact on the existing architecture and codebase, and without updating this document to reflect any changes in the development guidelines.
* **DO** Write clear and concise documentation for each backbone and data source module, including usage examples and explanations of the underlying algorithms, to facilitate understanding and ease of use for future contributors and users of the software.