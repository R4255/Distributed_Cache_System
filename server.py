#manages the TCP connections
import asyncio
import logging
from typing import Optional
from cache_node import CacheNode
from protocol import CacheProtocol

logger = logging.getLogger(__name__)

class CacheServer:
    '''
    Async TCP Server that Handles Cache Request
    '''
    def __init__(self, host: str = "localhost", port: int = 6379, cache_node: Optional[CacheNode] = None):
        self.host = host
        self.port = port
        self.cache_node = cache_node or CacheNode()
        self.protocol = CacheProtocol(self.cache_node)
        self.server = None
        
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handling the individual Client Connection"""
        client_addr = writer.get_extra_info('peername') #peername is ip and port 
        #reader handles data coming FROM the client (commands)
        #writer handles data going TO the client (responses)
        logger.info(f"CLient connected: {client_addr}")
        
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break
                
                command = data.decode().strip()
                if not command:
                    continue
                    
                logger.info(f"Command from {client_addr}: {command}")
                response = self.protocol.handle_command(command)
                writer.write(f"{response}\n".encode())
                
                #The client (like telnet) receives these bytes, converts them back to text, and displays the response. The newline helps the client know when the response is complete.
                await writer.drain()
                #await writer.drain() ensures that the data you just wrote is actually sent to the client.
                '''
                Buffering: When you call writer.write(), the data might be buffered in memory rather than immediately sent over the network
Flushing: drain() forces the buffer to be flushed, actually transmitting the data
Backpressure handling: If the network is slow or the client isn't reading fast enough, drain() will wait until there's space in the buffer
Async behavior: The await means this operation won't block other concurrent connections while waiting
                '''
        except asyncio.CancelledError:
            # Server is running with multiple client connections
            # User presses Ctrl+C or calls server.stop()
            # All client handler tasks get cancelled
            # Each raises CancelledError
            pass
        except Exception as e:
            logger.error(f"Error handling client {client_addr}: {e}")
        finally:
            logger.info(f"Closing Connection to {client_addr}")
            writer.close()
            await writer.wait_closed()
            '''writer.close()
                Initiates the connection closing process
                Tells the operating system to start shutting down the TCP connection
                Sends a FIN packet to the client indicating "no more data will be sent"
                This is non-blocking - it returns immediately
                await writer.wait_closed()
                Waits for the connection to be completely closed
                Ensures all buffered data is sent before closing
                Waits for the TCP handshake to complete (client acknowledges the close)
                This is async - won't block other connections while waiting
            '''
            
            
    async def start(self):
        '''Start the Cache Server'''
        # Creating and Starting the TCP Server
        self.server = await asyncio.start_server(
            self.handle_client,  # This is the callback that handles each client connection
            self.host, # The host to bind the server to
            self.port, # The port to listen on  
        )
        
        logger.info(f"Cache Server Started ON {self.host}:{self.port}")
        logger.info(f"Cache Configuration: max_size={self.cache_node.max_size}, "
            f"eviction_policy={self.cache_node.eviction_policy.value}")
        async with self.server:
            await self.server.serve_forever()
            
        '''serve_forever():

        Runs an infinite loop accepting client connections
        Each client gets handled concurrently by handle_client
        Only exits when cancelled or an exception occurs
        '''
    
    async def stop(self):
        '''Stop the Cache Server'''
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info(f"Cache Server Stopped")