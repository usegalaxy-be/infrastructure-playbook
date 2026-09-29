# Ansible role to init [KUI](https://github.com/galaxyproject/kui) installation

This role does:

 - [X] Install gcloud using [andrewrothstein.gcloud](https://galaxy.ansible.com/ui/standalone/roles/andrewrothstein/gcloud/) role
 - [X] Install KUI dependencies
 - [X] Clone the KUI
 - [X] Add a cron to launch KUI every month

This role doesn't:

 - Launch the different gcloud tasks:
   - `gcloud init`
   - `gcloud config set project anvil-cost-modeling` 
   - `gcloud auth application-default login`
 - Manage the Google Cloud authentifications

 