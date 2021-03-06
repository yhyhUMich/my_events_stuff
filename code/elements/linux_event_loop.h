#ifndef ELEMENTS_LINUX_EVENT_LOOP_H
#define ELEMENTS_LINUX_EVENT_LOOP_H

#include <string>
#include <map>
#include <sys/epoll.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netdb.h>
#include <boost/unordered_map.hpp>
#include "easy_time.h"


// TOD0
// 1) Add signal handling (when needed)
// 2) Optional use of zero_copy_buffer if we wish to reuse data downstream 

namespace elements
{
/*
Handler should have this interface to compile

class linux_event_loop_handler
{
   void on_udp_packet(int fd, const char * buf, int size, timestamp ts){}
   void on_tcp_packet(int fd, const char * buf, int size, timestamp ts){} 
   void on_timer(int fd, char *buf, int size, timestamp ts){}
   void register_linux_event_loop(linux_event_loop<linux_event_loop_handler> *p){}
   void on_disconnect(int fd)()
};
*/

enum con_type{ UDP = 1, TCP = 2, TIMER = 3};

struct connection {
   std::string ip;
   std::string port;
   con_type type;
   bool is_enabled;
   struct epoll_event ev;
};

template <typename handler>
class linux_event_loop
{
public:
    
    linux_event_loop(handler *h) : _fd_epoll(-1) , _handler(h)  
    { 
        _handler->register_linux_event_loop(this);
        init();
    }

    ~linux_event_loop(){}

    int add_udp(
        std::string ip, 
        std::string port, 
        int buffer_size, 
        bool is_mc, 
        bool enable);

    int add_tcp(
        std::string ip,
        std::string  port,
        int rec_buf_size, 
        int send_buf_size, 
        bool enabled);
    
    int add_timer(
        bool is_absolute, 
        elements::timestamp absolute_time, 
        elements::nanoseconds relative_time,
        elements::nanoseconds period, 
        bool enabled);

    int remove(int fd);

    int enable(int fd);
    int disable(int fd);

    void run();
    void stop();

    int write_tcp(int fd, std::string &msg);

    void print_connections();

 private:
    
    void init();
    
    static const int MAX_EVENTS = 200; 
    static const int MAX_BUFFER = 2000;
    
    boost::unordered_map<int, connection> _cons;
    int _fd_epoll; 
    handler * _handler;
    bool _is_running;

    // utilities
    static int  get_recv_buffer_size(int s);
    static bool set_recv_buffer_size(int s, int bufsize);
    static bool set_send_buffer_size(int s, int bufsize);
    static bool set_recv_timeout(int s, int timeout);
    static bool mc_join(int s, addrinfo *ailist);
    static int set_nonblock(int fd);
    static bool set_kernel_ts(int fd);
};

#include "linux_event_loop.hpp"
}

#endif // ELEMENTS_LINUX_EVENT_LOOP_H
