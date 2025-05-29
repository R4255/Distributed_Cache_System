import asyncio
import sys

class CacheClient:
    """Simple async client for testing the cache server"""
    
    def __init__(self, host='localhost', port=6379):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
    
    async def connect(self):
        """Connect to the cache server"""
        try:
            self.reader, self.writer = await asyncio.open_connection(
                self.host, self.port
            )
            print(f"Connected to {self.host}:{self.port}")
        except Exception as e:
            print(f"Failed to connect: {e}")
            raise
    
    async def send_command(self, command: str) -> str:
        """Send a command and get response"""
        if not self.writer:
            raise Exception("Not connected to server")
        
        # Send command
        self.writer.write(f"{command}\n".encode())
        await self.writer.drain()
        
        # Read response
        response = await self.reader.readline()
        return response.decode().strip()
    
    async def close(self):
        """Close connection"""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            print("Connection closed")

async def interactive_mode():
    """Interactive command-line client"""
    client = CacheClient()
    
    try:
        await client.connect()
        
        print("Cache client connected! Type commands or 'quit' to exit")
        print("Examples: SET key value, GET key, DEL key, STATS, KEYS")
        
        while True:
            try:
                command = input("> ").strip()
                
                if command.lower() in ['quit', 'exit', 'q']:
                    break
                
                if not command:
                    continue
                
                response = await client.send_command(command)
                print(response)
                
            except EOFError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
                
    finally:
        await client.close()

async def demo_mode():
    """Run a demonstration of cache features"""
    client = CacheClient()
    
    try:
        await client.connect()
        print("Running cache demonstration...\n")
        
        # Demo commands
        commands = [
            ("SET user:1 john", "Setting user:1 to john"),
            ("SET user:2 jane", "Setting user:2 to jane"),
            ("GET user:1", "Getting user:1"),
            ("GET user:2", "Getting user:2"),
            ("SET temp_key 'expires in 5 seconds' 5", "Setting key with 5 second TTL"),
            ("KEYS", "Listing all keys"),
            ("STATS", "Getting cache statistics"),
            ("DEL user:1", "Deleting user:1"),
            ("GET user:1", "Trying to get deleted key"),
            ("KEYS", "Listing keys after deletion"),
        ]
        
        for command, description in commands:
            print(f"{description}")
            print(f"Command: {command}")
            response = await client.send_command(command)
            print(f"Response: {response}")
            print("-" * 50)
            await asyncio.sleep(1)  # Pause between commands
        
        # Wait and check TTL
        print("Waiting 6 seconds to test TTL expiration...")
        await asyncio.sleep(6)
        
        response = await client.send_command("GET temp_key")
        print(f"GET temp_key after TTL: {response}")
        
        response = await client.send_command("KEYS")
        print(f"Keys after TTL expiration: {response}")
        
    finally:
        await client.close()

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        print("Starting demo mode...")
        asyncio.run(demo_mode())
    else:
        print("Starting interactive mode...")
        asyncio.run(interactive_mode())

if __name__ == "__main__":
    main()