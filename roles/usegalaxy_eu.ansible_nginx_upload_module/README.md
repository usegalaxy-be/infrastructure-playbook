# Ansible role for building the Nginx upload module

Ansible role for building Nginx upload module from module source code and installing it into Nginx for RHEL 9 systems.

This role was adapted from [nginx-upload-module](https://github.com/usegalaxy-au/infrastructure/tree/master/roles/nginx-upload-module)

### Role workflow

  1. Install `epel-release` package
  2. Enable `CRB` (PowerTools) repository
  3. Install `nginx` package from systems `AppStream` repository.
  4. Enable and start `nginx` service
  5. Build nginx upload module dynamically from the source code
  6. Adds the module to the nginx configuration file in `/etc/nginx/nginx.conf`
  7. Restart `nginx` service
  8. Clean up the build directory

### Requirements

- Rocky Linux 9 (Should also work on RHEL 9 derivatives)

#### Tested on

- Rocky Linux 9

### Role Variables

- **nginx_build_module_dir**: Directory to build Nginx upload module in (Default: `/var/ansible`)

- **nginx_upload_module_source_url**: Source code for Nginx upload module (Default: https://github.com/fdintino/nginx-upload-module/archive/refs/tags/2.3.0.tar.gz)

### Example Playbook

    ---
    - name: install Nginx and dynamically compile the upload module
      hosts: all
      become: true
      roles:
        - role: ansible-nginx-upload-module

**Note**: Upload module uses deprecated OpenSSL APIs (RHEL 9 systems uses OpenSSL 3.0.1) and this causes the build to fail because Nginx uses the `-Werror` and `-Werror=format-security` in the compile flags (this tells the compiler to fail when there are deprecated warnings). Removing these flags from the Makefile will build the upload module successfully. *This is automatically done by this ansible role when building the upload module.*