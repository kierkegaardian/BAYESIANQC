import "vue-router";

declare module "vue-router" {
  interface RouteMeta {
    helpTitle?: string;
    helpText?: string;
  }
}

