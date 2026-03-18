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
