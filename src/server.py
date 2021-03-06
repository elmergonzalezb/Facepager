from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import cgi
from PySide2.QtCore import QObject, Signal, Slot
from urllib.parse import urlparse, parse_qs, unquote

class Server(ThreadingHTTPServer, QObject):
    action = Signal(str, str, dict)

    def __init__(self, port, api):
        QObject.__init__(self)
        self.api = api
        HandlerClass = self.requestHandlerFactory(self.api.getState, self.actionCallback)
        ThreadingHTTPServer.__init__(self,('localhost', port), HandlerClass)
        self.action.connect(self.api.action)

    def actionCallback(self, action=None, filename=None, payload=None):
        self.action.emit(action, filename, payload)

    def requestHandlerFactory(self, stateCallback, actionCallback):
        """Factory method to pass parameters to request handler"""

        class CustomHandler(RequestHandler):
            def __init__(self, *args, **kwargs):
                self.stateCallback = stateCallback
                self.actionCallback = actionCallback
                super(RequestHandler, self).__init__(*args, **kwargs)

        return CustomHandler


class RequestHandler(BaseHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super(RequestHandler, self).__init__(*args, **kwargs)

    def send_answer(self, content, status=200, message=None):
        self.send_response(status, message)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

        if content is not None:
            response = json.dumps(content)
            self.wfile.write(response.encode('utf-8'))

    def parseAction(self):
        action = {}

        try:
            # Parse headers
            contenttype_value, contenttype_params = cgi.parse_header(self.headers.get('content-type',''))
            action['contenttype'] = contenttype_value

            # refuse to receive non-json content
            # if contenttype_value != 'application/json':
            #     self.send_response(400)
            #     self.end_headers()
            #     return

            # Parse path
            url = urlparse(self.path)
            action['path'] = url.path.strip("/").split("/")
            action['path'] = [unquote(x) for x in action['path']]
            action['action'] = action['path'].pop(0)

            # Parse query
            action['query'] = parse_qs(url.query)
            filenames = action['query'].get('filename')
            if filenames is not None:
                action['filename'] = filenames.pop()

            # Get post data
            length = int(self.headers.get('content-length'))
            action['body'] = json.loads(self.rfile.read(length))

        except Exception as e:
            action['error'] = str(e)

        return action

    # Sends back the state and database name
    def do_GET(self):
        """
        Get state

        The first component of the URL path is the snippet name.
        Supported snippets are : settings, log
        An empty snipped just returns the database name and the state
        """

        try:
            action = self.parseAction()
            response = self.stateCallback(action['action'])
        except:
            self.send_answer(None, 500, "Could not process request.")
        else:
            self.send_answer(response)


    def do_POST(self):
        """
        Execute actions

        The first component of the URL path is the action name.
        The following components are parameters.
        Additional data ist provided in the payload.
        """

        # Handle actions
        try:
            action = self.parseAction()

            # Open database
            if action['action'] == "database":
                if action.get('filename') is not None:
                    if action['query'].get('create', False):
                        self.actionCallback('createdatabase', filename=action.get('filename'))
                    else:
                        self.actionCallback('opendatabase', filename=action.get('filename'))
                    result = "ok"
                else:
                    result = "Missing filename."

            # Post nodes: csv file or nodes in the payload
            elif action['action'] == "nodes":
                if action.get('filename') is not None:
                    self.actionCallback('addcsv', filename=action.get('filename'))
                    result = "ok"
                elif action.get('body') is not None:
                    nodes = action['body'].get('nodes', [])
                    if not (type(nodes) is list):
                        nodes = [nodes]
                    self.actionCallback('addnodes', payload=nodes)
                    result = "ok"

            # Post settings: preset file or settings in the payload
            elif action['action'] == "settings":
                if action.get('filename') is not None:
                    self.actionCallback('loadpreset', filename=action.get('filename'))
                    result = "ok"
                elif action.get('body') is not None:
                    self.actionCallback('applysettings', payload=action.get('body'))
                    result = "ok"
                else:
                    result = "Missing filename or data."

            # Fetch data
            elif action['action'] == "fetchdata":
                self.actionCallback('fetchdata')
                result = "ok"

            else:
                self.send_answer(None, 404, "No valid action!")
                return False

            # Response
            response = self.stateCallback()
            response['result'] = result
        except Exception as e:
            self.send_answer(None, 500, "Server error!")
            return False
        else:
            self.send_answer(response)
            return True
