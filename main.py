import argparse
import asyncio
import logging
import colorlog
import sys
import configparser
import signal
import traceback
import uvloop
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

class App:
    def __init__(self, loop, logger, config):
        self.loop = loop
        self.log = logger
        self.background_tasks = []
        self.config = config
        self.log.info("Stratum proxy server starting")
        signal.signal(signal.SIGINT, self.terminate)
        signal.signal(signal.SIGTERM, self.terminate)
        self.loop.create_task(self.start())


    async def start(self):
        try:
            self.background_tasks.append(self.loop.create_task(self.watchdog()))
            self.stratum_server = await asyncio.start_server(self.handle_connection,
                                                             self.config["SERVER"]["host"],
                                                             self.config["SERVER"]["port"])
            for sock in self.stratum_server.sockets:
                self.log.info(f"🔌 Listen: {sock.getsockname()}")
            self.background_tasks.append(self.loop.create_task(self.stratum_server.serve_forever()))
        except Exception as err:
            self.log.error("Stratum proxy server start failed")
            self.log.error(str(traceback.format_exc()))
            self.terminate(None, None)


    async def handle_connection(self, reader, writer):
        s = writer.get_extra_info("socket")
        ip, port = s.getpeername()
        self.log.debug("New connection from %s:%s" % (ip, port))
        host = self.config["POOL"]["host"]
        port = self.config["POOL"]["port"]
        r, w = await asyncio.open_connection(host, port)
        tasks = [self.loop.create_task(self.forward("miner", reader, w)),
                 self.loop.create_task(self.forward("pool", r, writer))]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for p in pending:
            p.cancel()

        try:
           writer.close()
           await writer.wait_closed()
        except:
            pass
        try:
           w.close()
           await w.wait_closed()
        except:
            pass
        self.log.debug("Close connection with %s:%s" % (ip, port))

    async def forward(self, label, reader, writer):
        while True:
            try:
                data = await reader.readline()
            except (asyncio.IncompleteReadError,
                    ConnectionResetError,
                    BrokenPipeError,
                    ConnectionAbortedError,
                    TimeoutError,
                    OSError) as e:
                self.log.debug("%s connection error %s" % (label, e))
                break
            if data == b'':
                    self.log.debug("%s closed connection" % label)
                    break

            self.log.debug("%s: %s" % (label, str(data)))
            try:
                writer.write(data)
                await writer.drain()
            except (asyncio.IncompleteReadError,
                    ConnectionResetError,
                    BrokenPipeError,
                    ConnectionAbortedError,
                    TimeoutError,
                    OSError) as e:
                self.log.debug("%s connection error %s" % (label, e))
                break

    async def watchdog(self):
        while True:
            try:
                while True:
                    await asyncio.sleep(40)
                    self.log.debug("watchdog @@")
            except asyncio.CancelledError:
                self.log.debug("watchdog terminated")
                break
            except Exception as err:
                self.log.error(str(traceback.format_exc()))
                self.log.error("watchdog error %s " % err)

    def _exc(self, a, b, c):
        return

    def terminate(self, a, b):
        self.loop.create_task(self.terminate_coroutine())


    async def terminate_coroutine(self):
        sys.excepthook = self._exc
        self.log.error('Stop request received')
        for task in self.background_tasks:
            task.cancel()
        self.log.info("Stratum proxy server stopped")
        self.loop.stop()



def init(loop, argv):
    config_file = "stratum.conf"
    log_level = logging.INFO
    logger = colorlog.getLogger('pool')
    config = configparser.ConfigParser()
    config.read(config_file)

    logger.setLevel(log_level)
    ch = logging.StreamHandler()
    ch.setLevel(log_level)
    formatter = colorlog.ColoredFormatter('%(log_color)s%(asctime)s %(levelname)s: %(message)s (%(module)s:%(lineno)d)')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    try:
        config["SERVER"]["host"]
        config["SERVER"]["port"]
        config["POOL"]["host"]
        config["POOL"]["port"]
    except Exception as err:
        logger.critical("Configuration failed: %s" % err)
        logger.critical("Shutdown")
        sys.exit(0)
    logger.setLevel(log_level)
    logger.info("Start")




    app = App(loop, logger, config)
    return app


if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = init(loop, sys.argv[1:])
    loop.run_forever()
    pending = asyncio.all_tasks(loop)
    loop.run_until_complete(asyncio.gather(*pending))
    loop.close()