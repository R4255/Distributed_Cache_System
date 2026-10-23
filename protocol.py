#handles the GET/SET/DEL commands
import json
import logging
from cache_node import CacheNode

logger = logging.getLogger(__name__)

class CacheProtocol:
    '''
    Simple Text Based Protocol for Cache Operations.
    Commands:
    GET key
    SET key value [EX seconds]
    DEL key
    STATS
    KEYS
    '''
    def __init__(self, cache_node: CacheNode):
        self.cache = cache_node
        
    def handle_command(self, command:str) -> str:
        parts = command.strip().split()
        
        if not parts:
            return "ERROR Empty command"
        
        cmd = parts[0].upper()
        
        '''
            Reasons for using this type of return f"OK {json.dumps(value)}" if value is not None else "NULL"
            Simple text protocol: Makes it easy to debug and test (you can use telnet or netcat)
            Clean parsing: Clients can immediately identify success/failure
            Type preservation: JSON maintains data types and structures
            Standard format: Familiar to developers who've used Redis
            '''
        try:
            if cmd == "GET":
                if len(parts) != 2:
                    return "ERROR Invalid GET command, Requires at least one Argument"
                key = parts[1]
                value = self.cache.get(key)
                return f"OK {json.dumps(value)}" if value is not None else "NULL"
            
            
            elif cmd == "SET":
                if len(parts) < 3:
                    return "ERROR: SET command requires at least key and value"
                key = parts[1]
                value = " ".join(parts[2:])
                ttl = None
                # TTL only via an explicit "EX seconds" suffix (as in Redis), so a numeric value
                # like "SET answer 42" is stored as "42" instead of being mistaken for a TTL
                if len(parts) >= 5 and parts[-2].upper() == "EX":
                    try:
                        ttl = float(parts[-1])
                    except ValueError:
                        return "ERROR: EX requires a number of seconds"
                    if ttl <= 0:
                        return "ERROR: EX must be greater than 0"
                    value = " ".join(parts[2:-2])

                success = self.cache.set(key, value, ttl)
                return "OK" if success else "ERROR: Failed to set"
            
            elif cmd == "DEL":
                if len(parts) != 2:
                    return "ERROR: DEL Requires atleast one Argument"
                key = parts[1]
                success = self.cache.delete(key)
                return "OK" if success else "NOT FOUND"
            
            elif cmd == "STATS":
                stats = self.cache.stats()
                return f"OK {json.dumps(stats)}"
                
            elif cmd == "KEYS":
                keys = self.cache.keys()
                return f"OK {json.dumps(keys)}"
            
            else:
                return f"ERROR: Unknown Command {cmd}"
            
        except Exception as e:
            logger.error(f"Command Handling Error: {e}")
            return f"ERROR: {str(e)}"

            