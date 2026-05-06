const ws = new WebSocket('ws://localhost:8765');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    document.getElementById('esp_reading_value').textContent = data.value;
};

ws.onopen = () => console.log('Connected to BLE bridge');
ws.onerror = (e) => console.error('WebSocket error', e);
ws.onclose = () => console.log('Disconnected');