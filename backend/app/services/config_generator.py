from __future__ import annotations

from datetime import timezone
from urllib.parse import urlencode

from app.models.server import Server
from app.models.vpn_access import VpnAccess
from app.utils.naming import infer_channel_name, slugify_identifier
from app.utils.serialization import encode_tag, parse_json_field


class ConfigGenerator:
    def _format_traffic_limit(self, total_bytes: int) -> str | None:
        if total_bytes <= 0:
            return None
        gib = 1024 * 1024 * 1024
        mib = 1024 * 1024
        if total_bytes % gib == 0:
            return f"{total_bytes // gib} ГБ"
        if total_bytes % mib == 0:
            return f"{total_bytes // mib} МБ"
        return f"{total_bytes} байт"

    def generate_vless(self, *, server: Server, access: VpnAccess, inbound: dict, client_payload: dict) -> dict:
        protocol = inbound.get("protocol", "vless")
        if protocol != "vless":
            raise ValueError("MVP-генератор поддерживает только VLESS")

        stream_settings = parse_json_field(inbound.get("streamSettings"))
        network = stream_settings.get("network", "tcp")
        security = stream_settings.get("security", "none")
        transport_host = server.public_host or server.host
        transport_port = server.public_port or inbound.get("port") or server.port

        query: dict[str, str] = {"type": network, "encryption": "none"}
        if security and security != "none":
            query["security"] = security

        if security == "tls":
            tls_settings = parse_json_field(stream_settings.get("tlsSettings"))
            server_name = tls_settings.get("serverName") or server.public_host or server.host
            if server_name:
                query["sni"] = server_name
            alpn = tls_settings.get("alpn")
            if alpn:
                query["alpn"] = ",".join(alpn)

        if security == "reality":
            reality = parse_json_field(stream_settings.get("realitySettings"))
            reality_settings = parse_json_field(reality.get("settings"))
            server_names = reality.get("serverNames") or reality_settings.get("serverNames") or []
            server_name = reality_settings.get("serverName")
            if server_names:
                query["sni"] = server_names[0]
            elif server_name:
                query["sni"] = server_name

            fingerprint = reality.get("fingerprint") or reality_settings.get("fingerprint")
            if fingerprint:
                query["fp"] = fingerprint

            public_key = reality.get("publicKey") or reality_settings.get("publicKey")
            if public_key:
                query["pbk"] = public_key

            short_ids = reality.get("shortIds") or reality_settings.get("shortIds") or []
            if short_ids:
                query["sid"] = short_ids[0]

            spider_x = reality.get("spiderX") or reality_settings.get("spiderX")
            if spider_x:
                query["spx"] = spider_x

            pqv = (
                reality.get("pqv")
                or reality.get("mldsa65Verify")
                or reality_settings.get("pqv")
                or reality_settings.get("mldsa65Verify")
            )
            if pqv:
                query["pqv"] = pqv

        if network == "ws":
            ws_settings = parse_json_field(stream_settings.get("wsSettings"))
            if ws_settings.get("path"):
                query["path"] = ws_settings["path"]
            host_header = parse_json_field(ws_settings.get("headers")).get("Host")
            if host_header:
                query["host"] = host_header

        if network == "grpc":
            grpc_settings = parse_json_field(stream_settings.get("grpcSettings"))
            if grpc_settings.get("serviceName"):
                query["serviceName"] = grpc_settings["serviceName"]

        if network in {"httpupgrade", "xhttp", "splithttp"}:
            http_settings = parse_json_field(
                stream_settings.get("httpupgradeSettings") or stream_settings.get("xhttpSettings")
            )
            if http_settings.get("path"):
                query["path"] = http_settings["path"]
            if http_settings.get("host"):
                query["host"] = http_settings["host"]

        flow = client_payload.get("flow")
        if flow:
            query["flow"] = flow

        tag_prefix = slugify_identifier(inbound.get("remark") or server.code or server.name, default="node")
        tag = f"{tag_prefix}-{access.client_email}" if access.client_email else tag_prefix
        query_string = urlencode(query, doseq=True)
        uri = (
            f"vless://{access.client_uuid}@{transport_host}:{transport_port}"
            f"?{query_string}#{encode_tag(tag)}"
        )
        expiry_label = access.expiry_at.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
        channel_name = infer_channel_name(access.product_code)
        traffic_label = self._format_traffic_limit(int(client_payload.get("totalGB") or 0))
        config_text = (
            f"Конфигурация VLESS\n"
            f"Канал: {channel_name}\n"
            f"Сервер: {server.name}\n"
            f"Страна: {server.country}\n"
            f"Профиль: {access.client_email}\n"
            f"Срок действия: {expiry_label}"
        )
        if traffic_label:
            config_text += f"\nТрафик: {traffic_label}"
        return {"uri": uri, "text": config_text, "query": query}
