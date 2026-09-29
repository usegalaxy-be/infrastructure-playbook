#!/usr/bin/env python3
"""
Variable to Role Mapper for Ansible Deployment

This script scans group_vars and host_vars directories to map variables
to their respective Ansible roles based on naming conventions and the
requirements.yml file.

Usage: python3 scripts/map_variables_to_roles.py [--output VARIABLES.md]
"""

import os
import re
import yaml
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional


# Role-specific variable prefixes based on common Ansible role conventions
ROLE_PREFIXES = {
    # Galaxy roles
    'galaxy_': 'galaxyproject.galaxy',
    'galaxy_config': 'galaxyproject.galaxy',
    'galaxy_manage': 'galaxyproject.galaxy',
    'galaxy_create': 'galaxyproject.galaxy',
    'galaxy_separate': 'galaxyproject.galaxy',
    'galaxy_force': 'galaxyproject.galaxy',
    'galaxy_build': 'galaxyproject.galaxy',
    'galaxy_systemd': 'usegalaxy_eu.galaxy_systemd',
    'galaxy_tool': 'galaxyproject.galaxy / galaxyproject.galaxy-tools',
    'galaxy_conda': 'galaxyproject.galaxy / galaxyproject.miniconda',
    'galaxy_admin': 'galaxyproject.galaxy',
    'galaxy_user': 'galaxyproject.galaxy',
    'galaxy_group': 'galaxyproject.galaxy',
    'galaxy_virtualenv': 'galaxyproject.galaxy',
    'galaxy_commit': 'galaxyproject.galaxy',
    'galaxy_instance': 'galaxyproject.galaxy',
    'galaxy_brand': 'galaxyproject.galaxy',
    'galaxy_layout': 'galaxyproject.galaxy',
    'galaxy_root': 'galaxyproject.galaxy',
    'galaxy_server_dir': 'galaxyproject.galaxy',
    'galaxy_venv': 'galaxyproject.galaxy',
    'galaxy_config_dir': 'galaxyproject.galaxy',
    'galaxy_mutable': 'galaxyproject.galaxy',
    'galaxy_file_path': 'galaxyproject.galaxy',
    'galaxy_job': 'galaxyproject.galaxy',
    'galaxy_workflow': 'galaxyproject.galaxy',
    'galaxy_themes': 'usegalaxy_eu.galaxy_subdomains',
    'galaxy_ftp': 'galaxyproject.proftpd',
    'galaxy_db_connection': 'galaxyproject.galaxy',
    'galaxy_install_database': 'galaxyproject.galaxy',
    'galaxy_dynamic': 'galaxyproject.galaxy',
    'galaxy_additional_venv': 'galaxyproject.galaxy',
    
    # PostgreSQL
    'postgresql_': 'galaxyproject.postgresql',
    'postgres_': 'galaxyproject.postgresql / galaxyproject.postgresql_objects',
    'postgresql_objects_': 'galaxyproject.postgresql_objects',
    'postgresql_backup': 'pdg.postgres-backup',
    
    # HTCondor
    'condor_': 'usegalaxy_eu.htcondor',
    
    # Nginx
    'nginx_': 'galaxyproject.nginx',
    
    # Certbot
    'certbot_': 'usegalaxy_eu.certbot',
    
    # RabbitMQ
    'rabbitmq_': 'usegalaxy_eu.rabbitmqserver / community.rabbitmq',
    
    # InfluxDB
    'influxdb_': 'usegalaxy_eu.influxdb / usegalaxy_eu.influxdbserver',
    'influx_': 'usegalaxy_eu.influxdb / usegalaxy_eu.influxdbserver',
    
    # Grafana
    'grafana_': 'cloudalchemy.grafana / pdg.grafana',
    
    # Telegraf
    'telegraf_': 'dj-wasabi.telegraf',
    
    # TIaaS
    'tiaas_': 'galaxyproject.tiaas2 / pdg.tiaas2',
    
    # CVMFS
    'cvmfs_': 'galaxyproject.cvmfs',
    
    # Miniconda
    'miniconda_': 'galaxyproject.miniconda',
    'conda_': 'galaxyproject.miniconda',
    
    # Pulsar
    'pulsar_': 'galaxyproject.pulsar',
    
    # ProFTPD
    'proftpd_': 'galaxyproject.proftpd',
    
    # Redis
    'redis_': 'geerlingguy.redis',
    
    # Flower
    'flower_': 'usegalaxy_eu.flower / pdg.flower',
    
    # Docker
    'docker_': 'geerlingguy.docker',
    
    # TUS
    'tusd_': 'galaxyproject.tusd',
    'tus_': 'galaxyproject.tusd / usegalaxy_eu.rustus',
    'galaxy_tusd': 'galaxyproject.tusd',
    'galaxy_tus': 'galaxyproject.tusd / usegalaxy_eu.rustus',
    
    # TPV
    'tpv_': 'usegalaxy_eu.tpv_broker / usegalaxy_eu.tpv_auto_lint / custom',
    
    # gxadmin
    'gxadmin_': 'galaxyproject.gxadmin',
    
    # Sentry
    'sentry_': 'mvdbeek.sentry_selfhosted',
    
    # Chrony
    'chrony_': 'influxdata.chrony',
    
    # Pip/Python
    'pip_': 'hxr.install-to-venv / custom',
    
    # Minio
    'minio_': 'custom (backup configuration)',
    
    # GIE Proxy (Galaxy Interactive Environments)
    'gie_proxy': 'custom (GIE proxy configuration)',
    
    # Stats collection
    'stats_': 'pdg.galaxy_stats / custom',
    
    # Job metrics
    'job_metrics': 'galaxyproject.galaxy',
}

# Variables that don't follow standard prefixes
SPECIAL_VARIABLES = {
    'server_hostname': 'common / multiple roles',
    'hostname': 'common / multiple roles',
    'inventory_hostname': 'Ansible built-in',
    'internal_address': 'custom / network configuration',
    'deploy_env': 'custom / deployment configuration',
    'enable_quotas': 'galaxyproject.galaxy',
    'require_login': 'galaxyproject.galaxy',
    'allow_user_creation': 'galaxyproject.galaxy',
    'allow_user_deletion': 'galaxyproject.galaxy',
    'allow_user_impersonation': 'galaxyproject.galaxy',
    'allow_path_paste': 'galaxyproject.galaxy',
    'expose_dataset_path': 'galaxyproject.galaxy',
    'expose_user_name': 'galaxyproject.galaxy',
    'admin_users': 'galaxyproject.galaxy',
    'tool_filters': 'galaxyproject.galaxy',
    'tool_section_filters': 'galaxyproject.galaxy',
    'toolbox_filter_base_modules': 'galaxyproject.galaxy',
    'enable_oidc': 'galaxyproject.galaxy',
    'enable_beta_gdpr': 'galaxyproject.galaxy',
    'enable_celery_tasks': 'galaxyproject.galaxy',
    'celery_conf': 'galaxyproject.galaxy',
    'install_reference_data': 'custom (igegu.galaxy_extras)',
    'loc_files_list': 'custom (reference data configuration)',
    'custom_telegraf_env': 'dj-wasabi.telegraf / custom',
    'monitor_condor': 'hxr.monitor-cluster / custom',
    'handy_users': 'usegalaxy_eu.handy',
    'handy_groups': 'usegalaxy_eu.handy',
    'enable_powertools': 'usegalaxy_eu.handy',
    'shared_cert_dir': 'custom (certificate management)',
    'amqp_internal_connection': 'galaxyproject.galaxy',
    'id_secret': 'galaxyproject.galaxy',
    'smtp_server': 'galaxyproject.galaxy',
    'smtp_username': 'galaxyproject.galaxy',
    'smtp_password': 'galaxyproject.galaxy',
    'error_email_to': 'galaxyproject.galaxy',
    'email_from': 'galaxyproject.galaxy',
    'enable_tool_recommendations': 'galaxyproject.galaxy',
    'add_utilisation_info': 'pdg.galaxy_stats / custom',
    'add_daily_stats': 'pdg.galaxy_stats / custom',
}

# Words to exclude from commented variable names (not actual variables)
EXCLUDED_PATTERNS = [
    'TODO', 'NOTE', 'FIXME', 'BUG', 'HACK', 'XXX',
    'https', 'http', 'here', 'are', 'is', 'the', 'a', 'an',
    'note', 'todo', 'fixme', 'bug', 'hack', 'xxx',
    'class', 'type', 'function', 'default', 'value', 'assign',
    'environment', 'destinations', 'execution', 'handlers', 'resources',
    'testing', 'groups', 'environments', 'tools', 'limits', 'load',
    'version', 'command', 'rules_module', 'runner', 'workers',
    'tags', 'vhost', 'password', 'alias', 'all', 'condition',
    'documentation', 'config', 'database', 'host', 'port', 'ip',
    'bind', 'count', 'name', 'names', 'file', 'dir', 'path',
    'data', 'memory_limit', 'umask', 'start_timeout', 'stop_timeout',
    'enabled', 'enable', 'static', 'timeout', 'job', 'module',
    'container', 'env', 'options', 'proftpd', 'grafana', 'influx',
    'static_dir', 'load', 'error_or_timeout', 'error', 'timedelta',
    'nodata_or_nullvalues', 'regular', 'concurrent_render_limit',
    'root_url', 'isDefault', 'admin', 'access', 'domain', 'type',
    'url', 'editable', 'settings', 'api', 'oauth', 'token',
    'client', 'server', 'certificate', 'key', 'ssl', 'ca_',
    'RabbitMQ', 'Sentry', 'proftpd', 'Flower', 'flower',
    'Role', 'Proftpd', 'Roles',
]


def load_yaml_file(filepath: Path) -> dict:
    """Load a YAML file and return its contents."""
    try:
        with open(filepath, 'r') as f:
            content = yaml.safe_load(f)
            return content if content else {}
    except Exception as e:
        print(f"Warning: Could not load {filepath}: {e}")
        return {}


def extract_variables_from_file(filepath: Path) -> Set[str]:
    """Extract all variable names from a YAML file."""
    variables = set()
    content = load_yaml_file(filepath)
    
    if isinstance(content, dict):
        variables.update(content.keys())
    
    return variables


def extract_commented_variables(filepath: Path) -> Set[Tuple[str, str, int]]:
    """
    Extract commented out variables from a YAML file.
    
    Returns a set of tuples: (variable_name, line_content, line_number)
    Only returns lowercase variable names that look like actual Ansible variables.
    """
    commented_vars = set()
    
    try:
        with open(filepath, 'r') as f:
            content = f.read()
    except Exception as e:
        print(f"Warning: Could not read {filepath}: {e}")
        return commented_vars
    
    lines = content.split('\n')
    
    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        
        # Skip lines that are just comment markers or empty
        if not stripped or stripped == '#':
            continue
        
        # Check for commented variable definitions
        # Pattern: optional spaces + # + optional spaces + variable_name + : + anything
        match = re.match(r'^\s*#+\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:(.*)$', stripped)
        
        if match:
            var_name = match.group(1)
            value_part = match.group(2).strip()
            
            # Only include variables that:
            # 1. Start with lowercase letter (actual Ansible variables)
            # 2. Are not in the exclusion list
            # 3. Look like actual variable names (not words like "here", "are", etc.)
            
            # Skip if it starts with uppercase (likely a comment keyword)
            if var_name[0].isupper():
                continue
            
            # Skip if it matches exclusion patterns
            excluded = False
            for pattern in EXCLUDED_PATTERNS:
                if var_name.lower() == pattern.lower():
                    excluded = True
                    break
            if excluded:
                continue
            
            # Skip if it looks like a word rather than a variable
            # (too short, or contains common English word patterns)
            if len(var_name) < 3:
                continue
            
            # Skip if it starts with common non-variable prefixes
            if var_name.lower() in ['proftpd', 'grafana', 'flower', 'rabbitmq', 'influxdb', 
                                      'influx', 'sentry', 'nginx', 'docker', 'redis',
                                      'certbot', 'chrony', 'telegraf', 'condor', 'tiaas',
                                      'cvmfs', 'pulsar', 'miniconda', 'gxadmin', 'tiaas']:
                # These are role names, not variable names
                continue
            
            commented_vars.add((var_name, line.strip(), line_num))
    
    return commented_vars


def map_variable_to_role(var_name: str) -> str:
    """Map a variable name to its likely role."""
    # Check special variables first
    if var_name in SPECIAL_VARIABLES:
        return SPECIAL_VARIABLES[var_name]
    
    # Check prefixes
    for prefix, role in ROLE_PREFIXES.items():
        if var_name.startswith(prefix):
            return role
    
    # Check for vault variables
    if var_name.startswith('vault_'):
        return 'ansible-vault (encrypted secrets)'
    
    return 'unknown / custom'


def scan_directory(base_path: Path, dir_type: str) -> Dict[str, Dict[str, List[Tuple[str, str]]]]:
    """
    Scan a directory (group_vars or host_vars) and map variables to roles.
    
    Returns:
        Dict mapping files to {role: [(var_name, file_path), ...]}
    """
    result = defaultdict(lambda: defaultdict(list))
    
    if not base_path.exists():
        return result
    
    for item in base_path.iterdir():
        if item.is_file() and item.suffix in ['.yml', '.yaml']:
            rel_path = item.relative_to(base_path.parent)
            variables = extract_variables_from_file(item)
            
            for var in variables:
                role = map_variable_to_role(var)
                result[str(rel_path)][role].append((var, str(item)))
        
        elif item.is_dir():
            # Recursively scan subdirectories
            for subitem in item.rglob('*.yml'):
                rel_path = subitem.relative_to(base_path.parent)
                variables = extract_variables_from_file(subitem)
                
                for var in variables:
                    role = map_variable_to_role(var)
                    result[str(rel_path)][role].append((var, str(subitem)))
    
    return result


def scan_for_commented_variables(base_path: Path) -> Dict[str, Set[Tuple[str, str, int]]]:
    """
    Scan a directory for commented out variables.
    
    Returns:
        Dict mapping file paths to set of (variable_name, line_content, line_number)
    """
    result = defaultdict(set)
    
    if not base_path.exists():
        return result
    
    for item in base_path.rglob('*.yml'):
        commented = extract_commented_variables(item)
        if commented:
            result[str(item.relative_to(base_path.parent))] = commented
    
    return result


def find_duplicate_variables(group_vars_map: dict, host_vars_map: dict) -> Dict[str, List[Tuple[str, str]]]:
    """
    Find variables that are defined in multiple locations.
    
    Returns:
        Dict mapping variable names to list of (role, file_path) tuples
    """
    duplicates = defaultdict(list)
    
    for file_map in [group_vars_map, host_vars_map]:
        for file_path, role_map in file_map.items():
            for role, vars_list in role_map.items():
                for var_name, var_file in vars_list:
                    duplicates[var_name].append((role, file_path))
    
    # Filter to only variables defined in multiple places
    return {var: locations for var, locations in duplicates.items() if len(locations) > 1}


def generate_markdown_report(
    group_vars_map: dict, 
    host_vars_map: dict, 
    commented_vars: dict,
    duplicate_vars: dict,
    all_active_variables: dict,  # Dict mapping var_name -> set of (role, file_path)
    output_file: str
):
    """Generate a markdown report of the variable-to-role mapping."""
    
    with open(output_file, 'w') as f:
        f.write("# Ansible Variables to Roles Mapping\n\n")
        f.write("This document maps all variables in `group_vars` and `host_vars` to their ")
        f.write("respective Ansible roles.\n\n")
        f.write("**Generated:** Automatically by `scripts/map_variables_to_roles.py`\n\n")
        f.write("**Purpose:** This index helps identify which role each variable configures, ")
        f.write("making it easier to understand and maintain the Ansible deployment.\n\n")
        f.write("---\n\n")
        
        # Table of Contents
        f.write("## Table of Contents\n\n")
        f.write("1. [Group Variables](#group-variables)\n")
        f.write("2. [Host Variables](#host-variables)\n")
        f.write("3. [Commented Out Variables](#commented-out-variables)\n")
        f.write("4. [Duplicate Variables](#duplicate-variables)\n")
        f.write("5. [Role Index](#role-index)\n")
        f.write("6. [Variable Index (Alphabetical)](#variable-index-alphabetical)\n\n")
        f.write("---\n\n")
        
        # Group Variables Section
        f.write("## Group Variables\n\n")
        f.write("Variables defined in `group_vars/` that apply to groups of hosts.\n\n")
        
        for file_path in sorted(group_vars_map.keys()):
            f.write(f"### `{file_path}`\n\n")
            role_map = group_vars_map[file_path]
            
            for role in sorted(role_map.keys()):
                vars_list = sorted(role_map[role], key=lambda x: x[0])
                f.write(f"#### Role: `{role}`\n\n")
                f.write("| Variable | File |\n")
                f.write("|----------|------|\n")
                
                for var_name, var_file in vars_list:
                    f.write(f"| `{var_name}` | `{file_path}` |\n")
                
                f.write("\n")
            
            f.write("\n")
        
        # Host Variables Section
        f.write("---\n\n")
        f.write("## Host Variables\n\n")
        f.write("Variables defined in `host_vars/` that apply to specific hosts.\n\n")
        
        for file_path in sorted(host_vars_map.keys()):
            f.write(f"### `{file_path}`\n\n")
            role_map = host_vars_map[file_path]
            
            for role in sorted(role_map.keys()):
                vars_list = sorted(role_map[role], key=lambda x: x[0])
                f.write(f"#### Role: `{role}`\n\n")
                f.write("| Variable | File |\n")
                f.write("|----------|------|\n")
                
                for var_name, var_file in vars_list:
                    f.write(f"| `{var_name}` | `{file_path}` |\n")
                
                f.write("\n")
            
            f.write("\n")
        
        # Commented Out Variables Section
        f.write("---\n\n")
        f.write("## Commented Out Variables\n\n")
        f.write("Variables that have been commented out in YAML files. ")
        f.write("These may be deprecated, temporarily disabled, or serve as documentation.\n\n")
        
        if commented_vars:
            # Organize by file first, then by role
            # Group variables by file and role
            file_role_map = defaultdict(lambda: defaultdict(list))
            
            for file_path in sorted(commented_vars.keys()):
                role_vars = defaultdict(list)
                
                for var_name, line_content, line_num in sorted(commented_vars[file_path], key=lambda x: x[0]):
                    role = map_variable_to_role(var_name)
                    
                    # Check if this variable is defined elsewhere (uncommented)
                    if var_name in all_active_variables:
                        locations = all_active_variables[var_name]
                        defined_elsewhere = f"Yes ({len(locations)} locations)"
                    else:
                        defined_elsewhere = "No"
                    
                    role_vars[role].append((var_name, line_num, defined_elsewhere))
                
                file_role_map[file_path] = role_vars
            
            # Write out organized by file
            for file_path in sorted(file_role_map.keys()):
                f.write(f"### `{file_path}`\n\n")
                
                role_map = file_role_map[file_path]
                
                for role in sorted(role_map.keys()):
                    vars_list = sorted(role_map[role], key=lambda x: x[0])
                    f.write(f"#### Role: `{role}`\n\n")
                    f.write("| Variable | Line # | Defined Elsewhere |\n")
                    f.write("|----------|---------|-------------------|\n")
                    
                    for var_name, line_num, defined_elsewhere in vars_list:
                        f.write(f"| `{var_name}` | {line_num} | {defined_elsewhere} |\n")
                    
                    f.write("\n")
                
                f.write("\n")
        else:
            f.write("No commented out variables were found.\n\n")
        
        # Duplicate Variables Section
        f.write("---\n\n")
        f.write("## Duplicate Variables\n\n")
        f.write("Variables that are defined in multiple locations. ")
        f.write("These may cause conflicts or unintended behavior.\n\n")
        
        if duplicate_vars:
            # Sort by number of occurrences (most duplicates first)
            sorted_duplicates = sorted(
                duplicate_vars.items(), 
                key=lambda x: len(x[1]), 
                reverse=True
            )
            
            for var_name, locations in sorted_duplicates:
                f.write(f"### `{var_name}`\n\n")
                f.write(f"**Defined in {len(locations)} locations:**\n\n")
                f.write("| Role | File |\n")
                f.write("|------|------|\n")
                
                for role, file_path in sorted(locations, key=lambda x: x[1]):
                    f.write(f"| `{role}` | `{file_path}` |\n")
                
                f.write("\n")
        else:
            f.write("No duplicate variables were found.\n\n")
        
        # Role Index Section
        f.write("---\n\n")
        f.write("## Role Index\n\n")
        f.write("All roles referenced in this deployment and their associated variables.\n\n")
        
        # Collect all roles and their variables
        all_roles = defaultdict(list)
        
        for file_map in [group_vars_map, host_vars_map]:
            for file_path, role_map in file_map.items():
                for role, vars_list in role_map.items():
                    for var_name, var_file in vars_list:
                        all_roles[role].append((var_name, file_path))
        
        for role in sorted(all_roles.keys()):
            vars_list = sorted(set(all_roles[role]), key=lambda x: x[0])
            f.write(f"### `{role}`\n\n")
            f.write(f"**Number of variables:** {len(vars_list)}\n\n")
            f.write("| Variable | Defined In |\n")
            f.write("|----------|------------|\n")
            
            for var_name, file_path in vars_list:
                f.write(f"| `{var_name}` | `{file_path}` |\n")
            
            f.write("\n")
        
        # Alphabetical Variable Index
        f.write("---\n\n")
        f.write("## Variable Index (Alphabetical)\n\n")
        f.write("All variables in alphabetical order with their roles and locations.\n\n")
        
        # Collect all variables
        all_variables = []
        
        for file_map in [group_vars_map, host_vars_map]:
            for file_path, role_map in file_map.items():
                for role, vars_list in role_map.items():
                    for var_name, var_file in vars_list:
                        all_variables.append((var_name, role, file_path))
        
        all_variables = sorted(set(all_variables), key=lambda x: x[0])
        
        f.write("| Variable | Role | File |\n")
        f.write("|----------|------|------|\n")
        
        for var_name, role, file_path in all_variables:
            f.write(f"| `{var_name}` | `{role}` | `{file_path}` |\n")
        
        f.write("\n")
        
        # Footer
        f.write("---\n\n")
        f.write("**Note:** This document is automatically generated. ")
        f.write("To update it, run:\n\n")
        f.write("```bash\n")
        f.write("python3 scripts/map_variables_to_roles.py\n")
        f.write("```\n")


def main():
    parser = argparse.ArgumentParser(
        description='Map Ansible variables to their respective roles'
    )
    parser.add_argument(
        '--output',
        default='VARIABLES.md',
        help='Output markdown file (default: VARIABLES.md)'
    )
    parser.add_argument(
        '--base-dir',
        default='.',
        help='Base directory of the Ansible deployment (default: current directory)'
    )
    
    args = parser.parse_args()
    
    base_path = Path(args.base_dir)
    group_vars_path = base_path / 'group_vars'
    host_vars_path = base_path / 'host_vars'
    
    print("Scanning group_vars...")
    group_vars_map = scan_directory(group_vars_path, 'group_vars')
    
    print("Scanning host_vars...")
    host_vars_map = scan_directory(host_vars_path, 'host_vars')
    
    print("Scanning for commented out variables...")
    commented_vars_group = scan_for_commented_variables(group_vars_path)
    commented_vars_host = scan_for_commented_variables(host_vars_path)
    
    # Merge commented variables from both directories
    commented_vars = defaultdict(set)
    commented_vars.update(commented_vars_group)
    commented_vars.update(commented_vars_host)
    
    print("Finding duplicate variables...")
    duplicate_vars = find_duplicate_variables(group_vars_map, host_vars_map)
    
    # Build a complete set of all active variables
    all_active_variables = defaultdict(set)
    for var_name, locations in duplicate_vars.items():
        all_active_variables[var_name].update(locations)
    
    print(f"Generating report: {args.output}")
    generate_markdown_report(
        group_vars_map, 
        host_vars_map, 
        commented_vars, 
        duplicate_vars,
        all_active_variables,
        args.output
    )
    
    print(f"\n✓ Variable mapping complete! Report saved to: {args.output}")
    
    # Print summary statistics
    total_group_vars = sum(
        len(role_map[role]) 
        for role_map in group_vars_map.values() 
        for role in role_map
    )
    total_host_vars = sum(
        len(role_map[role]) 
        for role_map in host_vars_map.values() 
        for role in role_map
    )
    total_commented = sum(len(vars) for vars in commented_vars.values())
    total_duplicates = len(duplicate_vars)
    
    print(f"\nStatistics:")
    print(f"  - Group variables files: {len(group_vars_map)}")
    print(f"  - Host variables files: {len(host_vars_map)}")
    print(f"  - Total group variables: {total_group_vars}")
    print(f"  - Total host variables: {total_host_vars}")
    print(f"  - Total active variables: {total_group_vars + total_host_vars}")
    print(f"  - Files with commented variables: {len(commented_vars)}")
    print(f"  - Total commented variables: {total_commented}")
    print(f"  - Duplicate variables: {total_duplicates}")


if __name__ == '__main__':
    main()
