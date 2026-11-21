#!/bin/bash
cd "$(dirname "$0")"
containerlab destroy -t apartment.clab.yml --cleanup
