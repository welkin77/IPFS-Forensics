"""
异常传播检测模块
位置: core/analysis/anomaly_detector.py

功能：基于时序分析、统计方法和行为模式检测非法内容的异常传播
与现有 core/analysis/ 下的内容分析和ID画像模块并列
"""

import math
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

logger = logging.getLogger(__name__)


# ==================== 数据模型 ====================

class AlertLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnomalyType(Enum):
    RAPID_PROPAGATION = "rapid_propagation"
    BURST_ACTIVITY = "burst_activity"
    CROSS_PLATFORM = "cross_platform"
    COORDINATED_SHARING = "coordinated_sharing"
    NEW_PROVIDER_SURGE = "new_provider_surge"
    SUSPICIOUS_TIMING = "suspicious_timing"


@dataclass
class AnomalyAlert:
    alert_id: str
    anomaly_type: AnomalyType
    level: AlertLevel
    cid: str
    description: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metrics: Dict = field(default_factory=dict)
    related_entities: List[str] = field(default_factory=list)
    is_acknowledged: bool = False

    def to_dict(self) -> dict:
        return {
            'alert_id': self.alert_id,
            'anomaly_type': self.anomaly_type.value,
            'level': self.level.value,
            'cid': self.cid,
            'description': self.description,
            'timestamp': self.timestamp.isoformat(),
            'metrics': self.metrics,
            'related_entities': self.related_entities,
            'is_acknowledged': self.is_acknowledged
        }


@dataclass
class TimeSeriesPoint:
    timestamp: datetime
    value: float
    metadata: Dict = field(default_factory=dict)


# ==================== 时序工具 ====================

class TimeSeriesBuffer:
    """滑动窗口时序数据"""

    def __init__(self, max_points: int = 10000):
        self._data: deque = deque(maxlen=max_points)

    def add(self, timestamp: datetime, value: float, **metadata):
        self._data.append(TimeSeriesPoint(timestamp, value, metadata))

    def get_window(
        self, window_seconds: int, end_time: datetime = None
    ) -> List[TimeSeriesPoint]:
        end = end_time or datetime.utcnow()
        start = end - timedelta(seconds=window_seconds)
        return [p for p in self._data if start <= p.timestamp <= end]

    def count_in_window(self, window_seconds: int) -> int:
        return len(self.get_window(window_seconds))

    def values_in_window(self, window_seconds: int) -> List[float]:
        return [p.value for p in self.get_window(window_seconds)]

    def rate_per_minute(self, window_seconds: int = 3600) -> float:
        count = self.count_in_window(window_seconds)
        minutes = window_seconds / 60
        return count / minutes if minutes > 0 else 0

    def __len__(self):
        return len(self._data)


class EWMACalculator:
    """指数加权移动平均，用于动态基线"""

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha
        self.ewma: Optional[float] = None
        self.ewma_variance: Optional[float] = None

    def update(self, value: float) -> Tuple[float, float]:
        if self.ewma is None:
            self.ewma = value
            self.ewma_variance = 0.0
        else:
            diff = value - self.ewma
            self.ewma = self.alpha * value + (1 - self.alpha) * self.ewma
            self.ewma_variance = (
                (1 - self.alpha) * (self.ewma_variance + self.alpha * diff ** 2)
            )
        std = math.sqrt(self.ewma_variance) if self.ewma_variance > 0 else 0
        return self.ewma, std

    def is_anomalous(self, value: float, sigma: float = 3.0) -> bool:
        if self.ewma is None or self.ewma_variance is None:
            return False
        std = math.sqrt(self.ewma_variance) if self.ewma_variance > 0 else 0
        if std == 0:
            return False
        return abs(value - self.ewma) / std > sigma


# ==================== 异常检测器 ====================

class AnomalyDetector:
    """
    异常传播检测器

    六种检测策略：
    1. EWMA动态阈值快速传播检测
    2. 突发活动检测（短窗口 vs 长窗口）
    3. 跨平台传播检测
    4. 协同分享行为检测
    5. 提供者激增检测
    6. 可疑时间模式检测
    """

    def __init__(
        self,
        ewma_alpha: float = 0.3,
        z_score_threshold: float = 3.0,
        burst_window_seconds: int = 300,
        burst_threshold_multiplier: float = 5.0,
        rapid_propagation_window: int = 3600,
        coordinated_time_window: int = 60,
        min_data_points: int = 10
    ):
        self.ewma_alpha = ewma_alpha
        self.z_score_threshold = z_score_threshold
        self.burst_window = burst_window_seconds
        self.burst_multiplier = burst_threshold_multiplier
        self.rapid_window = rapid_propagation_window
        self.coordinated_window = coordinated_time_window
        self.min_data_points = min_data_points

        # 每个CID的时序
        self._cid_timeseries: Dict[str, TimeSeriesBuffer] = defaultdict(
            TimeSeriesBuffer
        )
        self._cid_ewma: Dict[str, EWMACalculator] = {}
        self._cid_platforms: Dict[str, Dict[str, List[datetime]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._cid_sharers: Dict[str, List[Tuple[str, datetime]]] = defaultdict(
            list
        )
        self._provider_history: Dict[str, TimeSeriesBuffer] = defaultdict(
            TimeSeriesBuffer
        )

        # 全局
        self._global_timeseries = TimeSeriesBuffer(max_points=100000)
        self._global_ewma = EWMACalculator(alpha=0.1)

        # 告警
        self.alerts: List[AnomalyAlert] = []
        self._alert_counter = 0
        self._alert_callbacks = []

    # ==================== 事件记录 ====================

    def record_event(
        self,
        cid: str,
        platform: str = 'unknown',
        author_id: str = 'unknown',
        timestamp: datetime = None,
        provider_count: int = 0
    ):
        """记录一次CID活动事件"""
        ts = timestamp or datetime.utcnow()
        self._cid_timeseries[cid].add(ts, 1.0, platform=platform)
        self._global_timeseries.add(ts, 1.0, cid=cid)
        self._cid_platforms[cid][platform].append(ts)
        self._cid_sharers[cid].append((author_id, ts))
        if provider_count > 0:
            self._provider_history[cid].add(ts, float(provider_count))

    def record_provider_count(self, cid: str, count: int):
        self._provider_history[cid].add(datetime.utcnow(), float(count))

    # ==================== 综合分析 ====================

    def analyze(self, cid: str) -> List[AnomalyAlert]:
        """对CID进行全面异常分析"""
        alerts = []

        detectors = [
            self._detect_rapid_propagation,
            self._detect_burst,
            self._detect_cross_platform,
            self._detect_coordinated_sharing,
            self._detect_provider_surge,
            self._detect_suspicious_timing,
        ]

        for detector in detectors:
            try:
                alert = detector(cid)
                if alert:
                    alerts.append(alert)
            except Exception as e:
                logger.error(f"检测器 {detector.__name__} 错误: {e}")

        for alert in alerts:
            self.alerts.append(alert)
            self._trigger_alert_callbacks(alert)

        return alerts

    def analyze_all(self) -> List[AnomalyAlert]:
        all_alerts = []
        for cid in list(self._cid_timeseries.keys()):
            all_alerts.extend(self.analyze(cid))
        return all_alerts

    # ==================== 检测方法 ====================

    def _detect_rapid_propagation(self, cid: str) -> Optional[AnomalyAlert]:
        """EWMA动态阈值快速传播检测"""
        ts = self._cid_timeseries.get(cid)
        if not ts or len(ts) < self.min_data_points:
            return None

        current_rate = ts.rate_per_minute(self.rapid_window)
        if cid not in self._cid_ewma:
            self._cid_ewma[cid] = EWMACalculator(alpha=self.ewma_alpha)

        ewma = self._cid_ewma[cid]
        ewma_val, ewma_std = ewma.update(current_rate)

        if ewma.is_anomalous(current_rate, sigma=self.z_score_threshold):
            z_score = (
                (current_rate - ewma_val) / ewma_std
                if ewma_std > 0 else 0
            )
            return self._create_alert(
                AnomalyType.RAPID_PROPAGATION,
                self._z_to_level(z_score),
                cid,
                f"CID {cid[:20]}... 传播速率异常: "
                f"当前 {current_rate:.2f}/min, "
                f"基线 {ewma_val:.2f}/min, Z={z_score:.2f}",
                metrics={
                    'current_rate': round(current_rate, 4),
                    'baseline': round(ewma_val, 4),
                    'z_score': round(z_score, 2),
                    'window_seconds': self.rapid_window
                }
            )
        return None

    def _detect_burst(self, cid: str) -> Optional[AnomalyAlert]:
        """突发活动检测"""
        ts = self._cid_timeseries.get(cid)
        if not ts or len(ts) < self.min_data_points:
            return None

        short_count = ts.count_in_window(self.burst_window)
        long_count = ts.count_in_window(86400)
        windows_in_day = 86400 / self.burst_window
        avg = long_count / windows_in_day if windows_in_day > 0 else 0

        if avg <= 0:
            return None

        ratio = short_count / avg
        if ratio > self.burst_multiplier and short_count >= 5:
            level = AlertLevel.HIGH if ratio > 10 else AlertLevel.MEDIUM
            return self._create_alert(
                AnomalyType.BURST_ACTIVITY, level, cid,
                f"CID {cid[:20]}... 突发: "
                f"{self.burst_window}s内 {short_count} 次，"
                f"日均的 {ratio:.1f}x",
                metrics={
                    'burst_count': short_count,
                    'avg_per_window': round(avg, 2),
                    'burst_ratio': round(ratio, 2)
                }
            )
        return None

    def _detect_cross_platform(self, cid: str) -> Optional[AnomalyAlert]:
        """跨平台传播检测"""
        platforms = self._cid_platforms.get(cid, {})
        if len(platforms) < 2:
            return None

        cutoff = datetime.utcnow() - timedelta(hours=6)
        recent = {}
        for plat, timestamps in platforms.items():
            cnt = sum(1 for t in timestamps if t > cutoff)
            if cnt > 0:
                recent[plat] = cnt

        if len(recent) >= 2:
            level = AlertLevel.HIGH if len(recent) >= 3 else AlertLevel.MEDIUM
            return self._create_alert(
                AnomalyType.CROSS_PLATFORM, level, cid,
                f"CID {cid[:20]}... 在 {len(recent)} 个平台传播: "
                f"{', '.join(recent.keys())}",
                metrics={
                    'platforms': recent,
                    'platform_count': len(recent),
                    'total_mentions': sum(recent.values())
                }
            )
        return None

    def _detect_coordinated_sharing(self, cid: str) -> Optional[AnomalyAlert]:
        """协同分享检测"""
        sharers = self._cid_sharers.get(cid, [])
        if len(sharers) < 3:
            return None

        sorted_sharers = sorted(sharers, key=lambda x: x[1])
        max_coord = 0
        coord_authors = set()

        for i in range(len(sorted_sharers)):
            start = sorted_sharers[i][1]
            end = start + timedelta(seconds=self.coordinated_window)
            authors = set()
            for aid, ts in sorted_sharers[i:]:
                if ts <= end:
                    authors.add(aid)
                else:
                    break
            if len(authors) > max_coord:
                max_coord = len(authors)
                coord_authors = authors

        if max_coord >= 3:
            level = (
                AlertLevel.CRITICAL if max_coord >= 10
                else AlertLevel.HIGH if max_coord >= 5
                else AlertLevel.MEDIUM
            )
            return self._create_alert(
                AnomalyType.COORDINATED_SHARING, level, cid,
                f"CID {cid[:20]}... 协同分享: "
                f"{max_coord} 个用户在 {self.coordinated_window}s 内分享",
                metrics={
                    'coordinated_count': max_coord,
                    'window_seconds': self.coordinated_window,
                },
                related_entities=list(coord_authors)
            )
        return None

    def _detect_provider_surge(self, cid: str) -> Optional[AnomalyAlert]:
        """提供者激增检测"""
        history = self._provider_history.get(cid)
        if not history or len(history) < 3:
            return None

        recent = history.values_in_window(3600)
        if len(recent) < 2:
            return None

        current = recent[-1]
        try:
            import numpy as np
            prev_avg = float(np.mean(recent[:-1]))
        except ImportError:
            prev_avg = sum(recent[:-1]) / len(recent[:-1])

        if prev_avg <= 0:
            return None

        ratio = current / prev_avg
        if ratio > 3.0 and current >= 5:
            level = AlertLevel.HIGH if ratio > 10 else AlertLevel.MEDIUM
            return self._create_alert(
                AnomalyType.NEW_PROVIDER_SURGE, level, cid,
                f"CID {cid[:20]}... 提供者激增: "
                f"{int(prev_avg)} -> {int(current)} ({ratio:.1f}x)",
                metrics={
                    'current': int(current),
                    'previous_avg': round(prev_avg, 1),
                    'surge_ratio': round(ratio, 2)
                }
            )
        return None

    def _detect_suspicious_timing(self, cid: str) -> Optional[AnomalyAlert]:
        """可疑时间检测（北京时间凌晨0-6点）"""
        ts = self._cid_timeseries.get(cid)
        if not ts or len(ts) < self.min_data_points:
            return None

        recent = ts.get_window(86400)
        if len(recent) < 5:
            return None

        night = 0
        for p in recent:
            hour_bj = (p.timestamp.hour + 8) % 24
            if 0 <= hour_bj < 6:
                night += 1

        ratio = night / len(recent)
        if ratio > 0.6 and night >= 5:
            return self._create_alert(
                AnomalyType.SUSPICIOUS_TIMING, AlertLevel.LOW, cid,
                f"CID {cid[:20]}... 深夜活动: "
                f"{ratio:.0%} 发生在凌晨0-6点",
                metrics={
                    'night_ratio': round(ratio, 3),
                    'night_count': night,
                    'total_24h': len(recent)
                }
            )
        return None

    # ==================== 辅助 ====================

    def _create_alert(
        self, atype, level, cid, desc,
        metrics=None, related_entities=None
    ) -> AnomalyAlert:
        self._alert_counter += 1
        return AnomalyAlert(
            alert_id=f"ALERT-{self._alert_counter:06d}",
            anomaly_type=atype,
            level=level,
            cid=cid,
            description=desc,
            metrics=metrics or {},
            related_entities=related_entities or []
        )

    def _z_to_level(self, z: float) -> AlertLevel:
        if z > 5:
            return AlertLevel.CRITICAL
        elif z > 4:
            return AlertLevel.HIGH
        elif z > 3:
            return AlertLevel.MEDIUM
        return AlertLevel.LOW

    def on_alert(self, callback):
        self._alert_callbacks.append(callback)

    def _trigger_alert_callbacks(self, alert):
        for cb in self._alert_callbacks:
            try:
                cb(alert)
            except Exception as e:
                logger.error(f"告警回调失败: {e}")

    # ==================== 查询 ====================

    def get_statistics(self) -> dict:
        level_counts = defaultdict(int)
        type_counts = defaultdict(int)
        for a in self.alerts:
            level_counts[a.level.value] += 1
            type_counts[a.anomaly_type.value] += 1
        return {
            'total_cids_monitored': len(self._cid_timeseries),
            'total_events': sum(len(t) for t in self._cid_timeseries.values()),
            'total_alerts': len(self.alerts),
            'by_level': dict(level_counts),
            'by_type': dict(type_counts),
            'unacknowledged': sum(1 for a in self.alerts if not a.is_acknowledged)
        }

    def get_alerts(
        self,
        level: AlertLevel = None,
        anomaly_type: AnomalyType = None,
        cid: str = None,
        limit: int = 100,
        unacknowledged_only: bool = False
    ) -> List[dict]:
        filtered = self.alerts
        if level:
            filtered = [a for a in filtered if a.level == level]
        if anomaly_type:
            filtered = [a for a in filtered if a.anomaly_type == anomaly_type]
        if cid:
            filtered = [a for a in filtered if a.cid == cid]
        if unacknowledged_only:
            filtered = [a for a in filtered if not a.is_acknowledged]
        filtered.sort(key=lambda a: a.timestamp, reverse=True)
        return [a.to_dict() for a in filtered[:limit]]

    def acknowledge_alert(self, alert_id: str) -> bool:
        for a in self.alerts:
            if a.alert_id == alert_id:
                a.is_acknowledged = True
                return True
        return False

    def get_cid_risk_score(self, cid: str) -> dict:
        """综合风险评分"""
        score = 0.0
        factors = {}

        # 传播速率 (0-0.3)
        ts = self._cid_timeseries.get(cid)
        if ts and len(ts) > 0:
            rate = ts.rate_per_minute(3600)
            rs = min(rate / 10, 0.3)
            score += rs
            factors['propagation_rate'] = round(rs, 3)

        # 跨平台 (0-0.25)
        plats = self._cid_platforms.get(cid, {})
        ps = min(len(plats) * 0.08, 0.25)
        score += ps
        factors['cross_platform'] = {
            'score': round(ps, 3),
            'platforms': list(plats.keys())
        }

        # 独立分享者 (0-0.25)
        sharers = self._cid_sharers.get(cid, [])
        unique = len(set(s[0] for s in sharers))
        ss = min(unique * 0.05, 0.25)
        score += ss
        factors['unique_sharers'] = {'score': round(ss, 3), 'count': unique}

        # 告警 (0-0.2)
        cid_alerts = [a for a in self.alerts if a.cid == cid]
        high = sum(
            1 for a in cid_alerts
            if a.level in (AlertLevel.HIGH, AlertLevel.CRITICAL)
        )
        als = min(high * 0.05 + len(cid_alerts) * 0.02, 0.2)
        score += als
        factors['alerts'] = {
            'score': round(als, 3),
            'total': len(cid_alerts),
            'high': high
        }

        final = round(min(score, 1.0), 3)
        risk_level = (
            'critical' if final >= 0.8
            else 'high' if final >= 0.6
            else 'medium' if final >= 0.4
            else 'low' if final >= 0.2
            else 'minimal'
        )

        return {
            'cid': cid,
            'risk_score': final,
            'risk_level': risk_level,
            'factors': factors,
            'calculated_at': datetime.utcnow().isoformat()
        }