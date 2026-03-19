export interface Admin {
  id: number;
  username: string;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  admin: Admin;
}

export interface SetupStatusResponse {
  is_initialized: boolean;
}

export interface DashboardSummary {
  total_bots: number;
  active_bots: number;
  total_servers: number;
  active_servers: number;
  active_clients: number;
  test_clients: number;
  expired_accesses: number;
  total_users: number;
}

export interface Server {
  id: string;
  code: string;
  name: string;
  country: string;
  region: string | null;
  host: string;
  public_host: string | null;
  scheme: string;
  port: number;
  public_port: number | null;
  panel_path: string;
  connection_type: string;
  auth_mode: string;
  username: string | null;
  inbound_id: number;
  client_flow: string | null;
  is_active: boolean;
  is_trial_enabled: boolean;
  weight: number;
  health_status: string;
  last_checked_at: string | null;
  last_error: string | null;
  tags: string[];
  capabilities: string[];
  notes: string | null;
  connection_aliases: string[];
  created_at: string;
  updated_at: string;
  has_password: boolean;
  has_token: boolean;
}

export interface ServerTestResult {
  ok: boolean;
  status: string;
  message: string;
  version: string | null;
  inbounds: Array<{
    id: number;
    remark: string | null;
    protocol: string;
    port: number | null;
    enabled: boolean | null;
  }>;
}

export interface ServerCountryLookupResponse {
  country: string;
  resolved_ip: string;
}

export interface ManagedBot {
  id: string;
  code: string;
  name: string;
  product_code: string;
  telegram_bot_username: string | null;
  welcome_text: string | null;
  help_text: string | null;
  is_active: boolean;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
  has_token: boolean;
}

export interface SiteManagedBot {
  id: string;
  code: string;
  name: string;
  telegram_bot_username: string | null;
}

export interface SiteTemplate {
  key: string;
  name: string;
  filename: string;
  description: string;
  source_path: string;
  placeholders: string[];
  is_default: boolean;
}

export interface SiteConnectionProbeResult {
  ok: boolean;
  message: string;
  hostname: string;
  os_name: string;
  os_version: string | null;
  kernel: string;
  machine: string | null;
  python_version: string | null;
  current_user: string;
  home_dir: string;
  is_root: boolean;
  sudo_available: boolean;
  package_manager: string | null;
}

export interface SitePreviewResult {
  html: string;
  telegram_url: string | null;
  warnings: string[];
}

export interface SiteDeploymentPlan {
  site_code: string;
  service_name: string;
  template_name: string;
  publish_mode: string;
  server_name: string;
  public_url: string;
  proxy_port: number;
  ssl_mode: string;
  remote_root: string;
  app_dir: string;
  nginx_config_path: string | null;
  systemd_unit_path: string;
  cloudflare_unit_path: string | null;
  cloudflare_url_file: string | null;
  cloudflare_log_file: string | null;
  deploy_steps: string[];
  warnings: string[];
}

export interface Site {
  id: string;
  code: string;
  name: string;
  publish_mode: string;
  domain: string | null;
  public_url: string | null;
  template_key: string;
  template_name: string;
  server_access_mode: string;
  server_host: string;
  server_port: number;
  server_username: string;
  proxy_port: number;
  deployment_status: string;
  ssl_mode: string;
  last_deployed_at: string | null;
  last_error: string | null;
  connection_snapshot: Record<string, unknown>;
  deployment_snapshot: Record<string, unknown>;
  managed_bot: SiteManagedBot;
  created_at: string;
  updated_at: string;
  has_password: boolean;
}

export interface SiteDeleteResult {
  site_id: string;
  site_name: string;
  deleted_from_admin: boolean;
  deleted_from_server: boolean;
  warnings: string[];
}

export interface TelegramUser {
  id: number;
  telegram_user_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  language_code: string | null;
  status: string;
  trial_used: boolean;
  trial_started_at: string | null;
  trial_ends_at: string | null;
  registered_at: string;
  created_at: string;
  updated_at: string;
}

export interface Access {
  id: string;
  product_code: string;
  access_type: string;
  protocol: string;
  status: string;
  inbound_id: number;
  client_uuid: string;
  client_email: string;
  remote_client_id: string;
  client_sub_id: string | null;
  device_limit: number;
  expiry_at: string;
  activated_at: string;
  deactivated_at: string | null;
  config_uri: string | null;
  config_text: string | null;
  config_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  server: Server;
  managed_bot?: ManagedBot | null;
  site?: {
    id: string;
    code: string;
    name: string;
    domain: string | null;
    public_url: string | null;
  } | null;
  telegram_user: TelegramUser | null;
}

export interface AccessConfig {
  access_id: string;
  config_uri: string;
  config_text: string;
  expires_at: string;
}

export interface AuditLog {
  id: number;
  actor_type: string;
  actor_id: string | null;
  event_type: string;
  entity_type: string;
  entity_id: string | null;
  level: string;
  message: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ApiErrorPayload {
  detail?: string;
}

export interface FreeKassaEndpoint {
  method: string;
  url: string;
}

export interface FreeKassaSettings {
  shop_id: number | null;
  has_secret_word: boolean;
  has_secret_word_2: boolean;
  require_source_ip_check: boolean;
  allowed_ips: string[];
  endpoints: {
    notification: FreeKassaEndpoint;
    success: FreeKassaEndpoint;
    failure: FreeKassaEndpoint;
  };
  notes: string[];
}

export interface SystemSettings {
  app_name: string;
  public_app_url: string;
  trial_duration_hours: number;
  site_trial_duration_hours: number;
  site_trial_total_gb: number;
  scheduler_interval_minutes: number;
  three_xui_timeout_seconds: number;
  three_xui_verify_ssl: boolean;
  bot_webhook_base_url: string | null;
  sources: Record<string, string>;
  warnings: string[];
  updated_at: string | null;
  freekassa: FreeKassaSettings | null;
}
