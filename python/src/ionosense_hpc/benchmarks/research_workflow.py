"""
python/src/ionosense_hpc/benchmarks/research_workflow.py
--------------------------------------------------------------------------------
Research workflow orchestration for comprehensive experiments.
Manages complete research pipelines with reproducibility guarantees.
"""

import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ionosense_hpc.benchmarks.base import BenchmarkContext, BenchmarkResult
from ionosense_hpc.benchmarks.suite import BenchmarkSuite, SuiteConfig
from ionosense_hpc.benchmarks.sweep import ParameterSweep
from ionosense_hpc.config.schemas import ExperimentMetadata, ResearchConfig
from ionosense_hpc.exceptions import (
    ReproducibilityError,
    WorkflowError,
    DependencyError,
    DataIntegrityError
)
from ionosense_hpc.utils import logger


@dataclass
class WorkflowStage:
    """Represents a stage in the research workflow."""
    
    name: str
    stage_type: str  # 'setup', 'benchmark', 'sweep', 'analysis', 'report'
    config: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error: Optional[str] = None


@dataclass
class WorkflowResult:
    """Complete result from a research workflow execution."""
    
    workflow_id: str
    metadata: ExperimentMetadata
    stages: List[WorkflowStage]
    results: Dict[str, Any]
    artifacts: Dict[str, Path]
    context: BenchmarkContext
    success: bool
    total_duration_s: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'workflow_id': self.workflow_id,
            'metadata': self.metadata.model_dump() if hasattr(self.metadata, 'model_dump') else dict(self.metadata),
            'stages': [
                {
                    'name': s.name,
                    'type': s.stage_type,
                    'status': s.status,
                    'duration_s': (s.end_time - s.start_time).total_seconds() if s.end_time and s.start_time else None,
                    'error': s.error
                }
                for s in self.stages
            ],
            'results': self.results,
            'artifacts': {k: str(v) for k, v in self.artifacts.items()},
            'context': self.context.to_dict(),
            'success': self.success,
            'total_duration_s': self.total_duration_s
        }


class ResearchWorkflow:
    """
    Orchestrates complete research experiments with reproducibility.
    
    This class manages the full lifecycle of research experiments, from
    environment setup through benchmarking, analysis, and reporting,
    ensuring full reproducibility and traceability.
    """
    
    def __init__(self, config: ResearchConfig | Dict[str, Any] | str):
        """
        Initialize research workflow.
        
        Args:
            config: ResearchConfig, dict, or path to config file
        """
        if isinstance(config, str):
            config = ResearchConfig.from_file(config)
        elif isinstance(config, dict):
            config = ResearchConfig(**config)
            
        self.config = config
        self.metadata = config.metadata
        self.context = BenchmarkContext()
        
        # Generate workflow ID
        self.workflow_id = f"{self.metadata.experiment_id}_{datetime.now():%Y%m%d_%H%M%S}"
        
        # Setup directories
        self.base_dir = Path(f"./experiments/{self.workflow_id}")
        self.setup_directories()
        
        # Initialize workflow stages
        self.stages: List[WorkflowStage] = []
        self.results: Dict[str, Any] = {}
        self.artifacts: Dict[str, Path] = {}
        
        # Save configuration
        self.save_configuration()
        
        logger.info(f"Research workflow initialized: {self.workflow_id}")
        logger.info(f"Experiment: {self.metadata.name}")
        logger.info(f"Standards: {', '.join(self.metadata.standards)}")
        
    def setup_directories(self):
        """Create directory structure for experiment."""
        directories = [
            self.base_dir,
            self.base_dir / "configs",
            self.base_dir / "data",
            self.base_dir / "results",
            self.base_dir / "reports",
            self.base_dir / "logs",
            self.base_dir / "checkpoints"
        ]
        
        for dir_path in directories:
            dir_path.mkdir(parents=True, exist_ok=True)
            
    def save_configuration(self):
        """Save complete configuration for reproducibility."""
        config_path = self.base_dir / "configs" / "research_config.json"
        self.config.to_file(str(config_path))
        self.artifacts['config'] = config_path
        
        # Also save as YAML for readability
        yaml_path = self.base_dir / "configs" / "research_config.yaml"
        with open(yaml_path, 'w') as f:
            yaml.dump(self.config.model_dump(), f, default=str)
            
    def add_stage(
        self,
        name: str,
        stage_type: str,
        config: Dict[str, Any],
        dependencies: List[str] = None
    ) -> WorkflowStage:
        """Add a stage to the workflow."""
        stage = WorkflowStage(
            name=name,
            stage_type=stage_type,
            config=config,
            dependencies=dependencies or []
        )
        
        # Validate dependencies
        existing_stages = {s.name for s in self.stages}
        for dep in stage.dependencies:
            if dep not in existing_stages:
                raise WorkflowError(
                    f"Stage '{name}' depends on non-existent stage '{dep}'",
                    workflow_stage=name
                )
                
        self.stages.append(stage)
        return stage
        
    def capture_environment(self) -> Dict[str, Any]:
        """Capture complete environment for reproducibility."""
        env = {
            'python_version': sys.version,
            'platform': sys.platform,
            'cwd': str(Path.cwd()),
            'path': sys.path.copy(),
            'env_vars': {
                k: v for k, v in os.environ.items()
                if k.startswith(('CUDA', 'IONO', 'PATH', 'PYTHON'))
            }
        }
        
        # Capture pip packages
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'freeze'],
                capture_output=True,
                text=True,
                check=True
            )
            env['pip_packages'] = result.stdout.strip().split('\n')
        except Exception as e:
            logger.warning(f"Failed to capture pip packages: {e}")
            
        # Capture conda environment if available
        if shutil.which('conda'):
            try:
                result = subprocess.run(
                    ['conda', 'list', '--json'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                env['conda_packages'] = json.loads(result.stdout)
            except Exception as e:
                logger.warning(f"Failed to capture conda packages: {e}")
                
        # Capture git info
        try:
            env['git'] = {
                'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip(),
                'branch': subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).decode().strip(),
                'dirty': bool(subprocess.check_output(['git', 'status', '--porcelain']).decode().strip())
            }
        except Exception:
            env['git'] = None
            
        # Save environment
        env_path = self.base_dir / "configs" / "environment.json"
        with open(env_path, 'w') as f:
            json.dump(env, f, indent=2, default=str)
        self.artifacts['environment'] = env_path
        
        return env
        
    def verify_reproducibility(self, reference_env: Dict[str, Any] | None = None) -> bool:
        """Verify that the current environment matches requirements."""
        current_env = self.capture_environment()
        
        if reference_env is None:
            # Load from config if available
            env_path = self.base_dir / "configs" / "environment.json"
            if env_path.exists():
                with open(env_path) as f:
                    reference_env = json.load(f)
            else:
                logger.warning("No reference environment for comparison")
                return True
                
        issues = []
        
        # Check Python version
        if reference_env.get('python_version') != current_env.get('python_version'):
            issues.append(f"Python version mismatch")
            
        # Check critical packages
        ref_packages = set(reference_env.get('pip_packages', []))
        cur_packages = set(current_env.get('pip_packages', []))
        
        missing = ref_packages - cur_packages
        if missing:
            issues.append(f"Missing packages: {', '.join(list(missing)[:5])}")
            
        # Check git state
        if reference_env.get('git') and current_env.get('git'):
            if reference_env['git']['commit'] != current_env['git']['commit']:
                issues.append("Git commit mismatch")
            if current_env['git']['dirty']:
                issues.append("Git repository has uncommitted changes")
                
        if issues:
            raise ReproducibilityError(
                "Environment reproducibility check failed",
                missing_info=issues
            )
            
        return True
        
    def run_stage(self, stage: WorkflowStage) -> Any:
        """Execute a single workflow stage."""
        logger.info(f"Running stage: {stage.name} ({stage.stage_type})")
        
        stage.status = "running"
        stage.start_time = datetime.now()
        
        try:
            if stage.stage_type == "setup":
                result = self._run_setup_stage(stage)
            elif stage.stage_type == "benchmark":
                result = self._run_benchmark_stage(stage)
            elif stage.stage_type == "sweep":
                result = self._run_sweep_stage(stage)
            elif stage.stage_type == "analysis":
                result = self._run_analysis_stage(stage)
            elif stage.stage_type == "report":
                result = self._run_report_stage(stage)
            else:
                raise WorkflowError(f"Unknown stage type: {stage.stage_type}")
                
            stage.status = "completed"
            stage.end_time = datetime.now()
            
            # Save checkpoint
            self._save_checkpoint(stage)
            
            return result
            
        except Exception as e:
            stage.status = "failed"
            stage.end_time = datetime.now()
            stage.error = str(e)
            
            logger.error(f"Stage '{stage.name}' failed: {e}")
            
            if not self.config.output_settings.get('continue_on_error', False):
                raise WorkflowError(
                    f"Stage '{stage.name}' failed",
                    workflow_stage=stage.name
                ) from e
                
            return None
            
    def _run_setup_stage(self, stage: WorkflowStage) -> Dict[str, Any]:
        """Run environment setup stage."""
        # Capture environment
        env = self.capture_environment()
        
        # Verify dependencies
        missing_deps = []
        for dep in self.config.metadata.dependencies:
            try:
                __import__(dep)
            except ImportError:
                missing_deps.append(dep)
                
        if missing_deps:
            raise DependencyError(
                "Missing required dependencies",
                missing_dependencies=missing_deps
            )
            
        return {'environment': env, 'dependencies_verified': True}
        
    def _run_benchmark_stage(self, stage: WorkflowStage) -> BenchmarkResult:
        """Run benchmark suite stage."""
        suite_config = SuiteConfig(**stage.config)
        suite_config.output_dir = str(self.base_dir / "results" / stage.name)
        
        suite = BenchmarkSuite(suite_config)
        results = suite.run()
        
        # Store results
        self.results[stage.name] = results
        
        # Save artifacts
        for result in suite.results:
            result_path = self.base_dir / "results" / stage.name / f"{result.name}.json"
            result_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(result_path, 'w') as f:
                json.dump(result.to_dict(), f, indent=2, default=str)
                
        return results
        
    def _run_sweep_stage(self, stage: WorkflowStage) -> List[Any]:
        """Run parameter sweep stage."""
        sweep = ParameterSweep(stage.config)
        sweep.output_dir = self.base_dir / "results" / stage.name
        
        results = sweep.run()
        
        # Store results
        self.results[stage.name] = results
        
        return results
        
    def _run_analysis_stage(self, stage: WorkflowStage) -> Dict[str, Any]:
        """Run analysis stage on collected results."""
        from ionosense_hpc.utils.benchmark_utils import ValidationHelper
        
        validator = ValidationHelper()
        analysis_results = {}
        
        # Analyze each result set
        for name, results in self.results.items():
            if isinstance(results, dict) and 'results' in results:
                # Suite results
                benchmark_results = results['results']
            elif isinstance(results, list):
                # Sweep results
                benchmark_results = results
            else:
                continue
                
            # Perform validation
            for result in benchmark_results:
                if isinstance(result, dict) and 'measurements' in result:
                    validation = validator.validate_measurements(
                        np.array(result['measurements']),
                        name=result.get('name', 'unknown')
                    )
                    
                    analysis_results[result['name']] = validation
                    
        # Save analysis
        analysis_path = self.base_dir / "results" / "analysis.json"
        with open(analysis_path, 'w') as f:
            json.dump(analysis_results, f, indent=2, default=str)
            
        self.artifacts['analysis'] = analysis_path
        
        return analysis_results
        
    def _run_report_stage(self, stage: WorkflowStage) -> Path:
        """Generate final report."""
        from ionosense_hpc.benchmarks.reporting import generate_comparative_report, ReportConfig
        
        report_config = ReportConfig(**stage.config)
        
        # Collect all results
        results_dir = self.base_dir / "results"
        
        # Generate report
        report_path = self.base_dir / "reports" / f"report.{report_config.output_format}"
        
        generate_comparative_report(
            results_dir,
            report_path,
            report_config
        )
        
        self.artifacts['report'] = report_path
        
        return report_path
        
    def _save_checkpoint(self, stage: WorkflowStage):
        """Save workflow checkpoint after stage completion."""
        checkpoint = {
            'workflow_id': self.workflow_id,
            'stage': stage.name,
            'timestamp': datetime.now().isoformat(),
            'stages_completed': [s.name for s in self.stages if s.status == "completed"],
            'results_summary': {k: type(v).__name__ for k, v in self.results.items()}
        }
        
        checkpoint_path = self.base_dir / "checkpoints" / f"{stage.name}.json"
        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint, f, indent=2)
            
    def run(self, stages: List[str] | None = None) -> WorkflowResult:
        """
        Execute the complete research workflow.
        
        Args:
            stages: Specific stages to run (None for all)
            
        Returns:
            WorkflowResult with all outputs
        """
        workflow_start = datetime.now()
        
        logger.info("="*60)
        logger.info(f"RESEARCH WORKFLOW: {self.metadata.name}")
        logger.info("="*60)
        logger.info(f"Experiment ID: {self.metadata.experiment_id}")
        logger.info(f"Researcher: {self.metadata.researcher}")
        logger.info(f"Standards: {', '.join(self.metadata.standards)}")
        
        # Verify reproducibility
        if self.config.reproducibility['verify_checksums']:
            try:
                self.verify_reproducibility()
                logger.info("✓ Reproducibility verification passed")
            except ReproducibilityError as e:
                logger.warning(f"⚠ Reproducibility warning: {e}")
                
        # Run stages
        stages_to_run = stages or [s.name for s in self.stages]
        
        for stage_name in stages_to_run:
            stage = next((s for s in self.stages if s.name == stage_name), None)
            if not stage:
                logger.warning(f"Stage '{stage_name}' not found")
                continue
                
            # Check dependencies
            for dep in stage.dependencies:
                dep_stage = next((s for s in self.stages if s.name == dep), None)
                if dep_stage and dep_stage.status != "completed":
                    logger.warning(f"Dependency '{dep}' not completed, skipping '{stage_name}'")
                    continue
                    
            # Run stage
            self.run_stage(stage)
            
        # Calculate total duration
        workflow_end = datetime.now()
        total_duration = (workflow_end - workflow_start).total_seconds()
        
        # Determine success
        failed_stages = [s for s in self.stages if s.status == "failed"]
        success = len(failed_stages) == 0
        
        # Create result
        result = WorkflowResult(
            workflow_id=self.workflow_id,
            metadata=self.metadata,
            stages=self.stages,
            results=self.results,
            artifacts=self.artifacts,
            context=self.context,
            success=success,
            total_duration_s=total_duration
        )
        
        # Save final result
        result_path = self.base_dir / "workflow_result.json"
        with open(result_path, 'w') as f:
            json.dump(result.to_dict(), f, indent=2, default=str)
            
        # Print summary
        self._print_summary(result)
        
        return result
        
    def _print_summary(self, result: WorkflowResult):
        """Print workflow execution summary."""
        print("\n" + "="*60)
        print(f"WORKFLOW SUMMARY: {self.metadata.name}")
        print("="*60)
        print(f"Status: {'SUCCESS' if result.success else 'FAILED'}")
        print(f"Duration: {result.total_duration_s:.1f} seconds")
        print(f"Stages: {len([s for s in result.stages if s.status == 'completed'])}/{len(result.stages)} completed")
        
        if result.artifacts:
            print("\nArtifacts:")
            for name, path in result.artifacts.items():
                print(f"  {name}: {path}")
                
        print(f"\nResults saved to: {self.base_dir}")


def create_research_workflow(
    name: str,
    researcher: str = None,
    description: str = None
) -> ResearchWorkflow:
    """
    Convenience function to create a standard research workflow.
    
    Args:
        name: Experiment name
        researcher: Researcher name
        description: Experiment description
        
    Returns:
        Configured ResearchWorkflow instance
    """
    metadata = ExperimentMetadata(
        experiment_id=f"exp_{datetime.now():%Y%m%d_%H%M%S}",
        name=name,
        description=description,
        researcher=researcher
    )
    
    config = ResearchConfig(metadata=metadata)
    
    workflow = ResearchWorkflow(config)
    
    # Add standard stages
    workflow.add_stage("setup", "setup", {})
    workflow.add_stage("benchmarks", "benchmark", {
        "benchmarks": ["latency", "throughput", "accuracy"]
    }, dependencies=["setup"])
    workflow.add_stage("analysis", "analysis", {}, dependencies=["benchmarks"])
    workflow.add_stage("report", "report", {
        "format": "pdf",
        "title": name
    }, dependencies=["analysis"])
    
    return workflow


import os

import numpy as np

if __name__ == '__main__':
    # Example usage
    workflow = create_research_workflow(
        name="Performance Optimization Study",
        researcher="Research Team",
        description="Comprehensive performance evaluation of ionosense-hpc"
    )
    
    result = workflow.run()
    
    print(f"\nWorkflow completed: {result.success}")