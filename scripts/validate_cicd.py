#!/usr/bin/env python3
"""
Local validation script for CI/CD pipeline configuration.
Checks that everything is set up correctly before pushing to GitHub.
"""

import sys
from pathlib import Path
import json
import yaml
import subprocess


def check_python_version():
    """Verify Python version >= 3.14"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 14):
        print(f"❌ Python version {version.major}.{version.minor} < 3.14")
        return False
    print(f"✅ Python version {version.major}.{version.minor}")
    return True


def check_project_structure():
    """Verify essential directories and files exist"""
    required_paths = [
        "api/main.py",
        "model/artifacts/model.onnx",
        "data/split/test.csv",
        "tests/test_data_utils.py",
        "tests/test_onnx_integration.py",
        "tests/test_api.py",
        "pyproject.toml",
        "docker/Dockerfile",
        ".github/workflows/ci-cd.yml",
    ]
    
    all_exist = True
    for path in required_paths:
        full_path = Path(path)
        if full_path.exists():
            print(f"✅ {path}")
        else:
            print(f"❌ MISSING: {path}")
            all_exist = False
    
    return all_exist


def check_dependencies():
    """Verify key dependencies are installed"""
    required_packages = [
        "fastapi",
        "onnxruntime",
        "pytest",
        "pandas",
        "numpy",
    ]
    
    all_installed = True
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ MISSING: {package}")
            all_installed = False
    
    return all_installed


def check_dockerfile():
    """Validate Dockerfile syntax"""
    dockerfile_path = Path("docker/Dockerfile")
    if not dockerfile_path.exists():
        print("❌ Dockerfile not found")
        return False
    
    # Basic checks
    content = dockerfile_path.read_text()
    checks = [
        ("FROM", "Base image"),
        ("WORKDIR", "Working directory"),
        ("RUN", "Run command"),
        ("EXPOSE", "Port exposure"),
        ("CMD", "Start command"),
    ]
    
    all_present = True
    for keyword, description in checks:
        if keyword in content:
            print(f"✅ Dockerfile has {description}")
        else:
            print(f"❌ Dockerfile missing {description}")
            all_present = False
    
    return all_present


def check_github_workflow():
    """Validate GitHub Actions workflow YAML"""
    workflow_path = Path(".github/workflows/ci-cd.yml")
    if not workflow_path.exists():
        print("❌ Workflow file not found")
        return False
    
    try:
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)
        
        # Check required top-level keys
        required_keys = ["name", "on", "jobs"]
        all_present = True
        for key in required_keys:
            if key in workflow:
                print(f"✅ Workflow has '{key}'")
            else:
                print(f"❌ Workflow missing '{key}'")
                all_present = False
        
        # Check essential jobs
        jobs = workflow.get("jobs", {})
        required_jobs = ["test", "build", "deploy"]
        for job_name in required_jobs:
            if job_name in jobs:
                print(f"✅ Job '{job_name}' defined")
            else:
                print(f"❌ Job '{job_name}' missing")
                all_present = False
        
        return all_present
    except yaml.YAMLError as e:
        print(f"❌ Workflow YAML error: {e}")
        return False


def run_tests():
    """Run pytest to verify tests pass"""
    print("\n📋 Running tests...")
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-q", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            print("✅ All tests passed")
            return True
        else:
            print(f"❌ Tests failed:\n{result.stdout}\n{result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ Tests timed out")
        return False
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False


def check_env_file():
    """Verify .env.example exists"""
    env_path = Path(".env.example")
    if env_path.exists():
        print("✅ .env.example found")
        return True
    else:
        print("❌ .env.example not found")
        return False


def check_docker_compose():
    """Validate docker-compose.yml"""
    compose_path = Path("docker/docker-compose.yml")
    if not compose_path.exists():
        print("❌ docker-compose.yml not found")
        return False
    
    try:
        with open(compose_path) as f:
            compose = yaml.safe_load(f)
        
        # Check required sections
        if "services" in compose:
            services = list(compose["services"].keys())
            print(f"✅ docker-compose.yml defines services: {', '.join(services)}")
            return True
        else:
            print("❌ docker-compose.yml missing 'services'")
            return False
    except yaml.YAMLError as e:
        print(f"❌ docker-compose YAML error: {e}")
        return False


def main():
    """Run all checks and report results"""
    print("=" * 60)
    print("CI/CD Pipeline Validation")
    print("=" * 60)
    
    checks = [
        ("Python Version", check_python_version),
        ("Project Structure", check_project_structure),
        ("Dependencies", check_dependencies),
        ("Dockerfile", check_dockerfile),
        ("GitHub Workflow", check_github_workflow),
        (".env.example", check_env_file),
        ("docker-compose.yml", check_docker_compose),
    ]
    
    results = {}
    for name, check_func in checks:
        print(f"\n[{name}]")
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"❌ Error during check: {e}")
            results[name] = False
    
    # Optional: Run tests if everything else passes
    if all(results.values()):
        print(f"\n[Tests]")
        run_tests()
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results.items():
        status = "✅" if passed else "❌"
        print(f"{status} {name}")
    
    all_passed = all(results.values())
    print("=" * 60)
    
    if all_passed:
        print("\n✅ All checks passed! Ready to push to GitHub.")
        print("\nNext steps:")
        print("1. Set GitHub secrets (DOCKER_USERNAME, DOCKER_PASSWORD)")
        print("2. Push to main or develop branch")
        print("3. Monitor workflow at: https://github.com/<owner>/<repo>/actions")
        return 0
    else:
        print("\n❌ Some checks failed. Fix issues before pushing.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
