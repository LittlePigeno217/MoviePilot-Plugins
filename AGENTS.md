# Project Rules

## 115 Plugin Development

- When developing or modifying a 115 plugin feature, reference the corresponding 115 plugin implementation in [DDSRem-Dev/MoviePilot-Plugins](https://github.com/DDSRem-Dev/MoviePilot-Plugins).
- Every feature must map to an appropriate reference implementation from that repository. Preserve compatible behavior, interfaces, and edge-case handling unless a documented project-specific requirement calls for a difference.

## Plugin Debugging

- During plugin development, always install and debug the plugin in the MoviePilot Docker Compose project on the NAS connected through the local `.ssh` configuration.
