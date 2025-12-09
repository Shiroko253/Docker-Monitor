#!/usr/bin/env python3
"""
Discord Webhook Docker 容器監控 v2
改進版:能更準確區分容器的停止原因(崩潰/正常停止/重啟)
"""

import docker
import requests
import time
import logging
from datetime import datetime
from typing import Dict, Optional
from threading import Thread

# ===== 配置區 =====
WEBHOOK_URL = "https://discord.com/api/webhooks/1442076849889869836/PZTS1q3_HDKsjIOiXg8vGYQjxuSJwME0363T2HtRWjFPKRs7PzyId6Z8O1pe-1YT4QUm"
MONITORED_CONTAINERS = ["main-bot", "reimu-bot", "flandre-bot"]
NETWORK_CHECK_INTERVAL = 60
NETWORK_THRESHOLD = 10 * 1024 * 1024
RESTART_DETECTION_WINDOW = 5  # 重啟檢測窗口(秒)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class ContainerState:
    """容器狀態追蹤器"""
    
    def __init__(self, name: str):
        self.name = name
        self.status = "unknown"
        self.exit_code = None
        self.restart_count = 0
        self.last_stop_time = None
        self.last_start_time = None
        self.is_restarting = False
        self.restart_policy = None
    
    def update_from_container(self, container):
        """從容器對象更新狀態"""
        if not container:
            self.status = "not_found"
            return
        
        container.reload()
        self.status = container.status
        
        # 獲取重啟策略
        restart_policy = container.attrs.get('HostConfig', {}).get('RestartPolicy', {})
        self.restart_policy = restart_policy.get('Name', 'no')
        
        # 獲取重啟次數
        self.restart_count = container.attrs.get('RestartCount', 0)
        
        # 獲取退出碼(如果容器已停止)
        if self.status == "exited":
            state = container.attrs.get('State', {})
            self.exit_code = state.get('ExitCode', None)
    
    def mark_stop(self, exit_code: Optional[int] = None):
        """標記容器停止"""
        self.last_stop_time = time.time()
        if exit_code is not None:
            self.exit_code = exit_code
        
        # 如果有重啟策略且不是exit_code 0,可能會重啟
        if self.restart_policy in ['always', 'unless-stopped', 'on-failure']:
            if exit_code != 0 or self.restart_policy == 'always':
                self.is_restarting = True
    
    def mark_start(self):
        """標記容器啟動"""
        self.last_start_time = time.time()
        self.is_restarting = False
        self.exit_code = None
    
    def check_restart_window(self) -> bool:
        """檢查是否在重啟窗口內"""
        if not self.last_stop_time:
            return False
        
        elapsed = time.time() - self.last_stop_time
        return elapsed < RESTART_DETECTION_WINDOW
    
    def get_stop_reason(self) -> str:
        """判斷停止原因"""
        if self.is_restarting or self.check_restart_window():
            return "restarting"
        
        if self.exit_code == 0:
            return "stopped_gracefully"
        elif self.exit_code is not None and self.exit_code > 0:
            return "crashed"
        else:
            return "stopped"

class DiscordNotifier:
    """Discord Webhook 通知器"""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.status_message_id = None
    
    def send_message(self, title: str, description: str, color: int, fields: list = None) -> Optional[str]:
        """發送 Discord 嵌入消息"""
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Docker 容器監控 v2"}
        }
        
        if fields:
            embed["fields"] = fields
        
        payload = {"embeds": [embed]}
        
        try:
            response = requests.post(self.webhook_url, json=payload, params={"wait": "true"})
            if response.status_code == 200:
                return response.json().get('id')
            else:
                logger.error(f"發送消息失敗: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"發送消息錯誤: {e}")
            return None
    
    def edit_message(self, message_id: str, title: str, description: str, color: int, fields: list = None):
        """編輯已發送的消息"""
        if not message_id:
            return
        
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Docker 容器監控 v2"}
        }
        
        if fields:
            embed["fields"] = fields
        
        payload = {"embeds": [embed]}
        edit_url = f"{self.webhook_url}/messages/{message_id}"
        
        try:
            response = requests.patch(edit_url, json=payload)
            if response.status_code != 200:
                logger.error(f"編輯消息失敗: {response.status_code}")
        except Exception as e:
            logger.error(f"編輯消息錯誤: {e}")
    
    def send_detailed_report(self, container_name: str, reason: str, state: ContainerState):
        """發送詳細的狀態變更報告"""
        reason_config = {
            "crashed": {
                "emoji": "💥",
                "title": "容器崩潰",
                "color": 0xFF0000,
                "description": f"容器異常退出 (退出碼: {state.exit_code})"
            },
            "stopped_gracefully": {
                "emoji": "🛑",
                "title": "容器正常停止",
                "color": 0xFFA500,
                "description": "容器正常關閉 (退出碼: 0)"
            },
            "restarting": {
                "emoji": "🔄",
                "title": "容器重啟中",
                "color": 0xFFFF00,
                "description": "容器正在自動重啟"
            },
            "started": {
                "emoji": "🟢",
                "title": "容器已啟動",
                "color": 0x00FF00,
                "description": "容器成功啟動並運行"
            },
            "stopped": {
                "emoji": "⚫",
                "title": "容器已停止",
                "color": 0x808080,
                "description": "容器已停止運行"
            }
        }
        
        config = reason_config.get(reason, reason_config["stopped"])
        
        fields = [
            {"name": "狀態", "value": state.status, "inline": True},
            {"name": "重啟策略", "value": state.restart_policy or "none", "inline": True},
            {"name": "重啟次數", "value": str(state.restart_count), "inline": True}
        ]
        
        if state.exit_code is not None:
            fields.append({"name": "退出碼", "value": str(state.exit_code), "inline": True})
        
        self.send_message(
            title=f"{config['emoji']} {config['title']}: {container_name}",
            description=config['description'],
            color=config['color'],
            fields=fields
        )
    
    def update_status_board(self, container_states: Dict[str, ContainerState]):
        """更新狀態面板"""
        fields = []
        
        for name, state in container_states.items():
            status_emoji = {
                "running": "🟢 運行中",
                "exited": "🔴 已停止",
                "paused": "🟡 已暫停",
                "restarting": "🔄 重啟中",
                "not_found": "❌ 不存在"
            }
            
            status_text = status_emoji.get(state.status, "⚪ 未知")
            
            extra_info = []
            if state.exit_code is not None:
                extra_info.append(f"退出碼: {state.exit_code}")
            if state.restart_count > 0:
                extra_info.append(f"重啟: {state.restart_count}次")
            
            value = status_text
            if extra_info:
                value += f"\n{' | '.join(extra_info)}"
            
            fields.append({
                "name": name,
                "value": value,
                "inline": True
            })
        
        description = f"最後更新: {datetime.now().strftime('%H:%M:%S')}"
        
        if self.status_message_id:
            self.edit_message(
                self.status_message_id,
                "📊 容器狀態總覽",
                description,
                0x0099FF,
                fields
            )
        else:
            self.status_message_id = self.send_message(
                "📊 容器狀態總覽",
                description,
                0x0099FF,
                fields
            )

class DockerMonitor:
    """Docker 容器監控器"""
    
    def __init__(self, notifier: DiscordNotifier, container_names: list):
        self.client = docker.from_env()
        self.notifier = notifier
        self.container_names = container_names
        self.container_states: Dict[str, ContainerState] = {}
        self.network_stats = {}
        
        # 初始化狀態追蹤器
        for name in container_names:
            self.container_states[name] = ContainerState(name)
    
    def get_container(self, name: str):
        """獲取容器對象"""
        try:
            return self.client.containers.get(name)
        except docker.errors.NotFound:
            return None
        except Exception as e:
            logger.error(f"獲取容器 {name} 錯誤: {e}")
            return None
    
    def get_network_stats(self, container) -> Optional[Dict]:
        """獲取容器網絡統計"""
        try:
            stats = container.stats(stream=False)
            networks = stats.get('networks', {})
            
            total_rx = sum(net.get('rx_bytes', 0) for net in networks.values())
            total_tx = sum(net.get('tx_bytes', 0) for net in networks.values())
            
            return {
                "rx_bytes": total_rx,
                "tx_bytes": total_tx,
                "total": total_rx + total_tx
            }
        except Exception as e:
            logger.error(f"獲取網絡統計錯誤: {e}")
            return None
    
    def check_network_fluctuation(self, name: str, container) -> bool:
        """檢查網絡波動"""
        current_stats = self.get_network_stats(container)
        
        if not current_stats or name not in self.network_stats:
            self.network_stats[name] = current_stats
            return False
        
        prev_stats = self.network_stats[name]
        rx_diff = current_stats['rx_bytes'] - prev_stats['rx_bytes']
        tx_diff = current_stats['tx_bytes'] - prev_stats['tx_bytes']
        total_diff = rx_diff + tx_diff
        
        self.network_stats[name] = current_stats
        
        if total_diff > NETWORK_THRESHOLD:
            rx_mb = rx_diff / 1024 / 1024
            tx_mb = tx_diff / 1024 / 1024
            
            self.notifier.send_message(
                title=f"📊 網絡流量通報: {name}",
                description=f"檢測到較大的網絡流量變化",
                color=0x0099FF,
                fields=[
                    {"name": "接收 (RX)", "value": f"{rx_mb:.2f} MB", "inline": True},
                    {"name": "發送 (TX)", "value": f"{tx_mb:.2f} MB", "inline": True},
                    {"name": "總計", "value": f"{(rx_mb + tx_mb):.2f} MB", "inline": True}
                ]
            )
            return True
        
        return False
    
    def network_monitor_thread(self):
        """網絡監控線程"""
        logger.info(f"網絡監控線程已啟動，檢查間隔: {NETWORK_CHECK_INTERVAL} 秒")
        
        while True:
            try:
                for name in self.container_names:
                    state = self.container_states[name]
                    if state.status == "running":
                        container = self.get_container(name)
                        if container:
                            self.check_network_fluctuation(name, container)
                
                time.sleep(NETWORK_CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"網絡監控錯誤: {e}")
                time.sleep(10)
    
    def listen_events(self):
        """即時監聽 Docker 事件"""
        logger.info("🚀 開始即時監控容器事件")
        logger.info(f"📋 監控容器: {', '.join(self.container_names)}")
        
        # 初始化容器狀態
        for name in self.container_names:
            container = self.get_container(name)
            self.container_states[name].update_from_container(container)
        
        # 發送啟動通知和狀態面板
        self.notifier.send_message(
            title="✅ 監控系統已啟動",
            description=f"正在即時監控 {len(self.container_names)} 個容器",
            color=0x00FF00,
            fields=[
                {"name": "監控模式", "value": "即時事件監聽 + 智能狀態判斷", "inline": True},
                {"name": "監控容器", "value": "\n".join(self.container_names), "inline": False}
            ]
        )
        
        self.notifier.update_status_board(self.container_states)
        
        # 啟動網絡監控線程
        network_thread = Thread(target=self.network_monitor_thread, daemon=True)
        network_thread.start()
        
        try:
            for event in self.client.events(decode=True):
                self.handle_event(event)
        except KeyboardInterrupt:
            logger.info("⏹️  監控已停止")
            self.notifier.send_message(
                title="⏹️ 監控系統已停止",
                description="監控程序已手動停止",
                color=0xFF0000
            )
    
    def handle_event(self, event: Dict):
        """處理 Docker 事件 - 改進版"""
        if event.get('Type') != 'container':
            return
        
        actor = event.get('Actor', {})
        attributes = actor.get('Attributes', {})
        container_name = attributes.get('name', 'unknown')
        action = event.get('Action')
        
        if container_name not in self.container_names:
            return
        
        logger.info(f"容器事件: {container_name} - {action}")
        
        state = self.container_states[container_name]
        container = self.get_container(container_name)
        
        # 根據不同的 action 處理
        if action == 'start':
            state.mark_start()
            state.update_from_container(container)
            self.notifier.send_detailed_report(container_name, "started", state)
            
        elif action == 'die':
            # 容器死亡,獲取退出碼
            exit_code = int(attributes.get('exitCode', -1))
            state.mark_stop(exit_code)
            state.update_from_container(container)
            
            # 等待一小段時間看是否會自動重啟
            time.sleep(1)
            
            reason = state.get_stop_reason()
            self.notifier.send_detailed_report(container_name, reason, state)
            
        elif action == 'stop':
            state.update_from_container(container)
            if not state.is_restarting:
                reason = state.get_stop_reason()
                self.notifier.send_detailed_report(container_name, reason, state)
        
        # 更新狀態面板
        self.notifier.update_status_board(self.container_states)

def main():
    """主程序"""
    if not WEBHOOK_URL or not WEBHOOK_URL.startswith("https://discord.com/api/webhooks/"):
        logger.error("❌ 無效的 Discord Webhook URL!")
        logger.error("請確保 WEBHOOK_URL 是完整的 Discord Webhook 地址")
        return
    
    logger.info("初始化 Docker 監控系統 v2...")
    
    notifier = DiscordNotifier(WEBHOOK_URL)
    monitor = DockerMonitor(notifier, MONITORED_CONTAINERS)
    
    monitor.listen_events()

if __name__ == "__main__":
    main()
