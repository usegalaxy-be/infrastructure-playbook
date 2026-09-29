#!/bin/bash
find /home/galaxy_master/tools/_conda/envs -maxdepth 1 -mindepth 1 -type f -exec tar zxvf {} -C / \;
