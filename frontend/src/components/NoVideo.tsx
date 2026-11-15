export function NoVideo({ backendConnected }: { backendConnected: boolean }) {
  return (
    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-1 bg-[#0b0d10] px-6 text-center">
      <p className="text-base font-medium text-gray-200">
        {backendConnected ? "Waiting for drone video" : "Can't reach the backend"}
      </p>
      <p className="max-w-sm text-sm text-gray-500">
        {backendConnected
          ? "Turn on the drone and join its WiFi network. Video starts within about 30 seconds."
          : "Check that the backend is running. This page reconnects by itself."}
      </p>
    </div>
  );
}
