const wsUrl = "wss://127.0.0.1:8765";
let socket;

// Chart configuration globals
let rollChart, pitchChart, yawChart;
const MAX_DATA_POINTS = 40; // Reduced slightly to look clean in narrower side-by-side configurations

function createOptions(yMin, yMax) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            x: {
                grid: { color: '#2b2b2b' },
                ticks: { color: '#777', display: false }
            },
            y: {
                grid: { color: '#2b2b2b' },
                ticks: { color: '#888' },
                min: yMin,
                max: yMax
            }
        },
        plugins: {
            legend: { display: false }
        },
        animation: false
    };
}

function initCharts() {
    const ctxR = document.getElementById('rollChart').getContext('2d');
    const ctxP = document.getElementById('pitchChart').getContext('2d');
    const ctxY = document.getElementById('yawChart').getContext('2d');
    rollChart = new Chart(ctxR, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                data: [],
                borderColor: '#00ffcc',
                backgroundColor: 'transparent',
                borderWidth: 2,
                pointRadius: 0
            }]
        },
        options: createOptions(-180, 180)
    });

    pitchChart = new Chart(ctxP, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                data: [],
                borderColor: '#ff007f',
                backgroundColor: 'transparent',
                borderWidth: 2,
                pointRadius: 0
            }]
        },
        options: createOptions(-180, 180)
    });

    yawChart = new Chart(ctxY, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                data: [],
                borderColor: '#ffcc00',
                backgroundColor: 'transparent',
                borderWidth: 2,
                pointRadius: 0
            }]
        },
        options: createOptions(-180, 180)
    });
}

function updateCharts(roll, pitch, yaw) {
    const timestampLabel = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

    // Push data to Roll
    rollChart.data.labels.push(timestampLabel);
    rollChart.data.datasets[0].data.push(roll);

    // Push data to Pitch
    pitchChart.data.labels.push(timestampLabel);
    pitchChart.data.datasets[0].data.push(pitch);

    // Push data to Yaw
    yawChart.data.labels.push(timestampLabel);
    yawChart.data.datasets[0].data.push(yaw);

    // Manage sliding window window array limits
    if (rollChart.data.labels.length > MAX_DATA_POINTS) {
        rollChart.data.labels.shift(); rollChart.data.datasets[0].data.shift();
        pitchChart.data.labels.shift(); pitchChart.data.datasets[0].data.shift();
        yawChart.data.labels.shift(); yawChart.data.datasets[0].data.shift();
    }

    // Synchronized layout redraw
    rollChart.update();
    pitchChart.update();
    yawChart.update();
}

function connectWebSocket() {
    socket = new WebSocket(wsUrl);

    const rollEl = document.getElementById("roll_val");
    const pitchEl = document.getElementById("pitch_val");
    const yawEl = document.getElementById("yaw_val");
    const rawEl = document.getElementById("esp_reading_value");
    const statusEl = document.getElementById("ws_status");

    socket.onopen = () => {
        statusEl.textContent = "Connected";
        statusEl.style.color = "#00ff00";
        console.log("[WS] Connected to Python pipeline");
    };

    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);

            rollEl.textContent = data.roll.toFixed(2);
            pitchEl.textContent = data.pitch.toFixed(2);
            yawEl.textContent = data.yaw.toFixed(2);
            rawEl.textContent = event.data;

            updateCharts(data.roll, data.pitch, data.yaw);

        } catch (err) {
            console.error("[WS] Error parsing incoming transmission payload:", err);
        }
    };

    socket.onclose = () => {
        statusEl.textContent = "Disconnected (Retrying...)";
        statusEl.style.color = "#ff0000";
        console.log("[WS] Connection lost. Attempting reconnect in 2 seconds...");
        setTimeout(connectWebSocket, 2000);
    };

    socket.onerror = (error) => {
        console.error("[WS] Socket error recorded:", error);
        socket.close();
    };
}

window.addEventListener("DOMContentLoaded", () => {
    initCharts();
    connectWebSocket();
});