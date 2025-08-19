// ==================================
// 설정 (Configuration)
// ==================================
const config = {
    apiEndpoint: '',
    refreshInterval: 2000,
    maxChartPoints: 30,
    maxLogEntries: 50,
    maxAlerts: 5,
};

// ==================================
// 이벤트 버스 (Event Bus)
// ==================================
const eventBus = {
    events: {},
    subscribe(eventName, callback) {
        if (!this.events[eventName]) {
            this.events[eventName] = [];
        }
        this.events[eventName].push(callback);
    },
    publish(eventName, data) {
        if (this.events[eventName]) {
            this.events[eventName].forEach(callback => callback(data));
        }
    }
};

// ==================================
// API 서비스 모듈 (apiService)
// ==================================
const apiService = {
    monitoringEnabled: true,
    fetchIntervalId: null,
    async fetchAllStats() {
        if (!this.monitoringEnabled) return;
        try {
            const response = await fetch(config.apiEndpoint + '/stats');
            if (!response.ok) {
               throw new Error("Backend communication error");
            }
            const combinedStats = await response.json();
            eventBus.publish('statsUpdated', { stats: combinedStats, isFetchSuccess: true });
        } catch (error) {
            eventBus.publish('fetchError', { error, isFetchSuccess: false });
        }
    },
    async resetAllStats() {
        // 이 기능은 현재 구현되지 않았습니다.
        console.warn('Reset stats functionality is not implemented in the backend.');
        return Promise.resolve(true);
    },
    start() {
        this.monitoringEnabled = true;
        this.fetchAllStats();
        if (this.fetchIntervalId) clearInterval(this.fetchIntervalId);
        this.fetchIntervalId = setInterval(() => this.fetchAllStats(), config.refreshInterval);
        eventBus.publish('log', { message: 'Monitoring started.' });
    },
    stop() {
        this.monitoringEnabled = false;
        if (this.fetchIntervalId) clearInterval(this.fetchIntervalId);
        eventBus.publish('log', { message: 'Monitoring paused.' });
    }
};

// ==================================
// 차트 모듈 (chartModule)
// ==================================
const chartModule = {
    charts: {},
    init() {
        const commonOptions = {
            responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
            scales: { x: { ticks: { color: '#fff' } }, y: { ticks: { color: '#fff' }, beginAtZero: true } }
        };
        this.charts.responseTime = new Chart(document.getElementById('responseTimeChart')?.getContext('2d'), {
            type: 'line',
            data: { labels: [], datasets: [{ data: [], borderColor: '#4ade80', backgroundColor: 'rgba(74,222,128,0.1)', tension: 0.4, fill: true }] },
            options: commonOptions
        });
        this.charts.throughput = new Chart(document.getElementById('throughputChart')?.getContext('2d'), {
            type: 'bar',
            data: { labels: [], datasets: [{ data: [], backgroundColor: '#3b82f6' }] },
            options: commonOptions
        });
        eventBus.subscribe('statsUpdated', ({ stats }) => this.update(stats));
        eventBus.subscribe('reset', () => this.reset());
    },
    update(stats) {
        const now = new Date().toLocaleTimeString();
        const updateChart = (chart, data) => {
            if (!chart) return;
            chart.data.labels.push(now);
            chart.data.datasets[0].data.push(data);
            if (chart.data.labels.length > config.maxChartPoints) {
                chart.data.labels.shift();
                chart.data.datasets[0].data.shift();
            }
            chart.update('none');
        };
        updateChart(this.charts.responseTime, stats?.['load-balancer']?.avg_response_time_ms || 0);
        updateChart(this.charts.throughput, stats?.['load-balancer']?.requests_per_second || 0);
    },
    reset() {
        Object.values(this.charts).forEach(chart => {
            if(chart) {
                chart.data.labels = [];
                chart.data.datasets[0].data = [];
                chart.update();
            }
        });
    }
};

// ==================================
// 상태 표시 모듈 (statusModule)
// ==================================
const statusModule = {
    elements: {},
    serviceDisplayNames: {
        'api-gateway': 'API Gateway', 'auth': 'Auth Service',
        'user_service': 'User Service', 'blog_service': 'Blog Service',
        'database': 'Database', 'cache': 'Cache' // [추가] 캐시
    },
    init() {
        this.elements = {
            // 전체 상태
            overallStatus: document.getElementById('overall-status'),
            activeServices: document.getElementById('active-services'),
            totalRequests: document.getElementById('total-requests'),
            successRate: document.getElementById('success-rate'),
            serverList: document.getElementById('server-list'),

            // [수정] 네트워크 통계 요소들을 모두 가져옵니다.
            currentRps: document.getElementById('current-rps'),
            avgResponseTime: document.getElementById('avg-response-time'),
            errorRate: document.getElementById('error-rate'),

            // [수정] 데이터 저장소 상태 요소들을 모두 가져옵니다.
            dbStatus: document.getElementById('db-status'),
            cacheHitRate: document.getElementById('cache-hit-rate'),
            activeSessions: document.getElementById('active-sessions'),
        };
        eventBus.subscribe('statsUpdated', ({ stats, isFetchSuccess }) => this.update(stats, isFetchSuccess));
        eventBus.subscribe('fetchError', ({ isFetchSuccess }) => this.update(null, isFetchSuccess));

        this.setInitialState();
    },
    setInitialState() {
        this.elements.overallStatus.textContent = 'CONNECTING...';
        this.elements.overallStatus.className = 'metric-value metric-warning';
        this.elements.totalRequests.textContent = '0';
        this.elements.successRate.textContent = '0.0%';
        this.elements.activeServices.textContent = '0/0';
        this.elements.currentRps.textContent = '0.0';
        this.elements.avgResponseTime.textContent = '0ms';
        this.elements.errorRate.textContent = '0.0%';
        this.elements.dbStatus.textContent = 'N/A';
        this.elements.cacheHitRate.textContent = '0.0%';
        this.elements.activeSessions.textContent = '0';
        this.elements.serverList.innerHTML = '';
    },
    update(stats, isFetchSuccess) {
        if (!isFetchSuccess || !stats) {
            this.elements.overallStatus.textContent = 'DISCONNECTED';
            this.elements.overallStatus.className = 'metric-value metric-danger';
            this.updateServerList(null, false);
            return;
        }

        const lbData = stats['load-balancer'];
        const serviceStates = this.updateServerList(stats, true);
        const healthyCount = serviceStates.filter(s => s.isHealthy).length;
        const totalCount = serviceStates.length;

        // 전체 상태 업데이트
        this.elements.totalRequests.textContent = (lbData?.total_requests || 0).toLocaleString();
        this.elements.successRate.textContent = `${(lbData?.success_rate || 0).toFixed(1)}%`;
        this.elements.activeServices.textContent = `${healthyCount}/${totalCount}`;

        if (healthyCount < totalCount) {
            this.elements.overallStatus.textContent = 'DEGRADED';
            this.elements.overallStatus.className = 'metric-value metric-danger';
        } else if ((lbData?.success_rate || 100) < 95) {
            this.elements.overallStatus.textContent = 'WARNING';
            this.elements.overallStatus.className = 'metric-value metric-warning';
        } else {
            this.elements.overallStatus.textContent = 'HEALTHY';
            this.elements.overallStatus.className = 'metric-value metric-good';
        }

        this.elements.currentRps.textContent = (lbData?.requests_per_second || 0).toFixed(1);
        this.elements.avgResponseTime.textContent = `${(lbData?.avg_response_time_ms || 0).toFixed(1)}ms`;
        this.elements.errorRate.textContent = `${(100 - (lbData?.success_rate || 100)).toFixed(1)}%`;

        const dbIsHealthy = stats?.database?.status === 'healthy';
        this.elements.dbStatus.textContent = dbIsHealthy ? 'ONLINE' : 'OFFLINE';
        this.elements.dbStatus.className = `metric-value ${dbIsHealthy ? 'metric-good' : 'metric-danger'}`;
        this.elements.cacheHitRate.textContent = `${(stats?.cache?.hit_ratio || 0).toFixed(1)}%`;
        this.elements.activeSessions.textContent = stats?.auth?.active_session_count || 0;
    },
    updateServerList(stats, isLbHealthy) {
        // ... (이전과 동일한 리팩터링된 함수) ...
        const serverListElement = this.elements.serverList;
        if (!serverListElement) return [];
        serverListElement.innerHTML = '';

        const allServiceStates = [];
        allServiceStates.push({ name: 'Load Balancer', isHealthy: isLbHealthy });

        if (stats) {
            for (const key in this.serviceDisplayNames) {
                if (stats[key]) {
                    const serviceData = stats[key];
                    const isHealthy = serviceData.status === 'healthy' || serviceData.service_status === 'online';
                    allServiceStates.push({ name: this.serviceDisplayNames[key], isHealthy: isHealthy });
                }
            }
        }
        allServiceStates.forEach(service => {
            const li = document.createElement('li');
            li.className = 'server-item';
            const statusClass = service.isHealthy ? 'status-healthy' : 'status-error';
            li.innerHTML = `<span><span class="status-indicator ${statusClass}"></span>${service.name}</span><span>${service.isHealthy ? 'Online' : 'Offline'}</span>`;
            serverListElement.appendChild(li);
        });

        return allServiceStates;
    }
};

// ==================================
// 알림 모듈 (alertModule)
// ==================================
const alertModule = {
    init() {
        eventBus.subscribe('statsUpdated', ({ stats }) => this.checkAlerts(stats));
    },
    checkAlerts(stats) {
        const lbData = stats?.['load-balancer'];
        if (!lbData) return;

        if (lbData.success_rate < 95) this.addAlert('warning', `Success rate is low: ${lbData.success_rate.toFixed(1)}%`);
        if (lbData.avg_response_time_ms > 500) this.addAlert('warning', `High response time: ${lbData.avg_response_time_ms.toFixed(1)}ms`);

        // 전체 서비스 상태를 확인하여 다운된 서비스 알림
        const serviceStates = statusModule.updateServerList(stats, true);
        const downServices = serviceStates.filter(s => !s.isHealthy);
        if (downServices.length > 0) {
            this.addAlert('error', `${downServices.map(s => s.name).join(', ')} service(s) are down.`);
        }
    },
    addAlert(type, message) {
        const container = document.getElementById('alerts-container');
        if (!container) return;
        const alertExists = [...container.children].some(child => child.textContent.includes(message));
        if (alertExists) return;
        const alert = document.createElement('li');
        alert.className = `alert-box alert-${type}`;
        alert.innerHTML = `<strong>${type.toUpperCase()}:</strong> ${message}`;
        container.insertBefore(alert, container.firstChild);
        if (container.children.length > config.maxAlerts) {
            container.removeChild(container.lastChild);
        }
    }
};

// ==================================
// 컨트롤 모듈 (controlsModule)
// ==================================
const controlsModule = {
    init() {
        document.getElementById('toggle-monitoring-btn')?.addEventListener('click', this.toggleMonitoring.bind(this));
        document.getElementById('refresh-btn')?.addEventListener('click', this.refresh);
        document.getElementById('reset-stats-btn')?.addEventListener('click', this.reset);
    },
    toggleMonitoring(event) {
        const btn = event.currentTarget;
        apiService.monitoringEnabled = !apiService.monitoringEnabled;
        if (apiService.monitoringEnabled) {
            btn.textContent = '모니터링 ON';
            btn.classList.add('active');
            apiService.start();
        } else {
            btn.textContent = '모니터링 OFF';
            btn.classList.remove('active');
            apiService.stop();
        }
    },
    async reset() {
        eventBus.publish('log', { message: 'Resetting statistics...' });
        const success = await apiService.resetAllStats();
        if (success) {
            eventBus.publish('log', { message: 'Statistics have been reset.' });
            eventBus.publish('reset');
            await apiService.fetchAllStats();
        } else {
            eventBus.publish('log', { message: 'Failed to reset stats.', type: 'error' });
        }
    },
    refresh() {
        eventBus.publish('log', { message: 'Manual refresh triggered.' });
        apiService.fetchAllStats();
    }
};

// ==================================
// 유틸리티 모듈 (utilityModule)
// ==================================
const utilityModule = {
    startTime: Date.now(),
    init() {
        eventBus.subscribe('log', ({ message, type = 'info' }) => this.addLog(message, type));
        eventBus.subscribe('fetchError', ({ error }) => this.addLog(`[ERROR] ${error.message}`, 'error'));
        setInterval(() => this.updateTime(), 1000);
    },
    addLog(message, type = 'info') {
        const logsContainer = document.getElementById('logs-container');
        if (!logsContainer) return;
        const logEntry = document.createElement('div');
        logEntry.className = 'log-entry';
        logEntry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
        logEntry.style.color = type === 'error' ? '#f87171' : '#ecf0f1';
        logsContainer.insertBefore(logEntry, logsContainer.firstChild);
        if (logsContainer.children.length > config.maxLogEntries) {
            logsContainer.removeChild(logsContainer.lastChild);
        }
    },
    updateTime() {
        const uptimeElem = document.getElementById('uptime');
        const timeElem = document.getElementById('current-time');
        if (timeElem) timeElem.textContent = new Date().toLocaleString();
        if (uptimeElem) {
            const uptime = Date.now() - this.startTime;
            const h = String(Math.floor(uptime / 3600000)).padStart(2, '0');
            const m = String(Math.floor((uptime % 3600000) / 60000)).padStart(2, '0');
            const s = String(Math.floor((uptime % 60000) / 1000)).padStart(2, '0');
            uptimeElem.textContent = `Uptime: ${h}:${m}:${s}`;
        }
    }
};

// ==================================
// 메인 실행 함수 (Main Entry Point)
// ==================================
function main() {
    chartModule.init();
    statusModule.init();
    alertModule.init();
    controlsModule.init();
    utilityModule.init();
    eventBus.publish('log', { message: 'Monitoring dashboard initialized.' });
    apiService.start();
}

document.addEventListener('DOMContentLoaded', main);