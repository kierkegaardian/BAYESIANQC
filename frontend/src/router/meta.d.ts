import "vue-router";

import type { Permission } from "../api/contracts";

declare module "vue-router" {
  interface RouteMeta {
    helpTitle?: string;
    helpText?: string;
    hideHelp?: boolean;
    requiredPermission?: Permission;
    stakeholderVisible?: boolean;
  }
}
