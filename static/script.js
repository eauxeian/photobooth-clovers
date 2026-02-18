// Connect to Socket.IO
const socket = io();

// ===== QUEUE PAGE =====
socket.on("queue_update", function (data) {
    const queueContainer = document.getElementById("queue-container");
    const adminContainer = document.getElementById("admin-dashboard");

    // ---------------------
    // PUBLIC QUEUE PAGE
    // ---------------------
    if (queueContainer) {
        queueContainer.innerHTML = "";

        if (!data.pending || data.pending.length === 0) {
            queueContainer.innerHTML = "<p>No pending orders.</p>";
            return;
        }

        data.pending.forEach(order => {
            const card = document.createElement("div");
            card.className = "queue-card";

            card.innerHTML = `
                <h3>Queue #${order.QueueNumber}</h3>
                <p><strong>Order ID:</strong> ${order.ID}</p>
                <p><strong>Type:</strong> ${order["Order Type"]}</p>
                <p><strong>Quantity:</strong> ${order.Quantity}</p>
                <hr>
            `;

            queueContainer.appendChild(card);
        });
    }

    // ---------------------
    // ADMIN DASHBOARD
    // ---------------------
    if (adminContainer) {
        adminContainer.innerHTML = "";

        if (!data.all || data.all.length === 0) {
            adminContainer.innerHTML = "<p>No orders found.</p>";
            return;
        }

        data.all.forEach(order => {
            const card = document.createElement("div");
            card.className = "admin-card";

            card.innerHTML = `
                <h4>ID: ${order.ID}</h4>
                <p><strong>Name:</strong> ${order.Name}</p>
                <p><strong>Type:</strong> ${order["Order Type"]}</p>
                <p><strong>Status:</strong> ${order.Status}</p>
                <p><strong>Printed:</strong> ${order.Printed}</p>
                <p><strong>Claimed:</strong> ${order.Claimed}</p>

                <form method="POST" action="/toggle/${order.ID}">
                    <button type="submit">Toggle Status</button>
                </form>

                <form method="POST" action="/toggle_printed/${order.ID}">
                    <button type="submit">Toggle Printed</button>
                </form>

                <form method="POST" action="/toggle_claimed/${order.ID}">
                    <button type="submit">Toggle Claimed</button>
                </form>

                <form method="POST" action="/clear/${order.ID}">
                    <button type="submit">Hide Order</button>
                </form>

                <hr>
            `;

            adminContainer.appendChild(card);
        });
    }
});

// Optional: Debug connection
socket.on("connect", function () {
    console.log("Connected to server");
});
