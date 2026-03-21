from water.server import FlowServer
from branched_flow import notification_flow
from loop_flow import retry_flow
from parallel_flow import send_notification_flow
from sequential_flow import registration_flow

# Create server with flows
app = FlowServer(flows=[notification_flow, retry_flow, send_notification_flow, registration_flow]).get_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("playground:app", host="0.0.0.0", port=8000, reload=True)