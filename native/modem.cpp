// PocketJS8 Lite native JS8 modem bridge.
// SPDX-License-Identifier: GPL-3.0-or-later
// Links against gfsk8-modem-clean at a PINNED upstream revision.
// No JS8Call GUI, Qt, Dire Wolf, or remote machine is involved.
#include "gfsk8modem.h"
#include "DecodedText.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <optional>
#include <sstream>
#include <span>
#include <stdexcept>
#include <string_view>
#include <string>
#include <thread>
#include <vector>

namespace {
constexpr int kRate = 12000;
constexpr int kPeriod = 15;
constexpr size_t kRing = static_cast<size_t>(kRate) * 60;

std::string escape_json(std::string const &input) {
    std::ostringstream ss;
    for (unsigned char c : input) {
        switch (c) {
        case '"': ss << "\\\""; break;
        case '\\': ss << "\\\\"; break;
        case '\n': ss << "\\n"; break;
        case '\r': ss << "\\r"; break;
        case '\t': ss << "\\t"; break;
        default:
            if (c < 0x20) {
                ss << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                   << static_cast<int>(c) << std::dec;
            } else ss << static_cast<char>(c);
        }
    }
    return ss.str();
}
std::mutex output_mutex;
void emit(std::string const &event) {
    std::lock_guard<std::mutex> lock(output_mutex);
    std::cout << event << '\n' << std::flush;
}

std::optional<std::string> flag(int argc, char **argv, std::string_view arg) {
    for (int i = 2; i + 1 < argc; ++i)
        if (argv[i] == arg) return argv[i+1];
    return std::nullopt;
}

int seconds_utc(std::time_t t) {
    std::tm out{};
    if (!gmtime_r(&t, &out)) return 0;
    return out.tm_hour*3600 + out.tm_min*60 + out.tm_sec;
}

struct RxSession {
    std::vector<int16_t> ring = std::vector<int16_t>(kRing, 0);
    size_t head=0, received=0;
    std::thread worker;
    std::mutex mutex;
    std::condition_variable cond;
    std::vector<int16_t> snapshot;
    bool pending=false, stopped=false, busy=false;
    std::atomic<unsigned> dropped{0};

    void add(int16_t const *data, size_t n) {
        for (size_t i=0; i<n; ++i) {
            ring[head] = data[i];
            head=(head+1)%kRing;
        }
        received+=n;
    }
    void queue(std::time_t wall_time) {
        if (received < static_cast<size_t>(kRate) * kPeriod) return;
        std::unique_lock lock(mutex);
        if (pending || busy) {
            dropped.fetch_add(1);
            return;
        }
        // Oldest sample first, newest last; fixed 60-second snapshot.
        snapshot.resize(kRing);
        for (size_t i=0;i<kRing;++i) snapshot[i]=ring[(head+i)%kRing];
        pending=true;
        int const nutc=seconds_utc(wall_time);
        captured_time=nutc;
        lock.unlock();
        cond.notify_one();
    }
    int captured_time=0;
    void work() {
        // Construct once: a decoder allocates substantial FFT state.
        gfsk8::Decoder decoder(1 << 0, 200, 3000); // NORMAL ONLY, 200–3000 Hz
        emit("{\"event\":\"ready\",\"mode\":\"normal\"}");
        for (;;) {
            std::vector<int16_t> local;
            int t=0;
            {
                std::unique_lock lock(mutex);
                cond.wait(lock, [this]{return pending || stopped;});
                if (stopped && !pending) break;
                local.swap(snapshot);
                t=captured_time;
                pending=false;
                busy=true;
            }
            try {
                decoder.decode(std::span<const int16_t>(local.data(),local.size()), t,
                    [&](gfsk8::Decoded const &d) {
                        DecodedText decoded(d.message, d.frameType, d.submode);
                        std::ostringstream msg;
                        msg << "{\"event\":\"decode\",\"utc\":" << t
                            << ",\"text\":\"" << escape_json(decoded.message()) << "\""
                            << ",\"raw\":\"" << escape_json(d.message) << "\""
                            << ",\"snr\":" << d.snrDb
                            << ",\"offset\":" << static_cast<int>(std::round(d.frequencyHz))
                            << ",\"dt\":" << std::fixed << std::setprecision(2) << d.dtSeconds
                            << ",\"low_confidence\":" << (decoded.isLowConfidence()?"true":"false")
                            << "}";
                        emit(msg.str());
                    });
            } catch (std::exception const &e) {
                emit("{\"event\":\"error\",\"message\":\"decode failed\"}");
                std::cerr << e.what() << '\n';
            }
            {
                std::lock_guard lock(mutex);
                busy=false;
            }
        }
    }
};

int receive() {
    // Read 12 kHz mono S16_LE from stdin continuously.
    // The audio reader never blocks on a heavy decode; each 15-second
    // snapshot is sent to a dedicated worker. Old work is NOT queued up.
    RxSession sess;
    sess.worker = std::thread([&sess] { sess.work(); });
    std::array<int16_t, 1024> chunk{};
    auto last_boundary = static_cast<std::time_t>(-1);
    int rc=0;
    for (;;) {
        size_t n=std::fread(chunk.data(), sizeof(int16_t),chunk.size(),stdin);
        if (n==0) {
            if (std::ferror(stdin)) rc=1;
            break;
        }
        sess.add(chunk.data(),n);
        // Snap after a UTC 15-second boundary, once per period.
        // Read-side audio buffering adds latency; offset measurement and
        // hardware validation remain required on the actual sound card.
        auto now = std::chrono::system_clock::now();
        auto t=std::chrono::system_clock::to_time_t(now);
        auto boundary=t-(t%kPeriod);
        auto since = std::chrono::duration<double>(now.time_since_epoch()).count()-static_cast<double>(boundary);
        if (since>=0.20 && last_boundary!=boundary) {
            sess.queue(t);
            last_boundary=boundary;
            if (sess.dropped.load()>0 && sess.dropped.load()%2==1)
                emit("{\"event\":\"warning\",\"message\":\"decoder cannot keep up\"}");
        }
    }
    {
        std::lock_guard lock(sess.mutex); sess.stopped=true;
    }
    sess.cond.notify_one();
    if (sess.worker.joinable()) sess.worker.join();
    return rc;
}

std::vector<gfsk8::TxFrame> packed(int argc, char **argv) {
    auto call=flag(argc,argv,"--call");
    auto grid=flag(argc,argv,"--grid");
    auto message=flag(argc,argv,"--message");
    if (!call || !grid || !message) throw std::runtime_error("--call, --grid, --message required");
    return gfsk8::pack(*call,*grid,*message,gfsk8::Submode::Normal);
}

int frames(int argc, char **argv) {
    auto result=packed(argc,argv);
    std::cout << "{\"frames\":" << result.size() << ",\"seconds_per_frame\":15}" << '\n';
    return result.empty()?2:0;
}

int tx(int argc, char **argv) {
    auto idx=flag(argc,argv,"--index");
    if (!idx) throw std::runtime_error("--index required");
    int index=std::stoi(*idx);
    auto all=packed(argc,argv);
    if (index<0 || static_cast<size_t>(index)>=all.size()) throw std::runtime_error("bad frame index");
    auto const &frame=all[static_cast<size_t>(index)];
    auto pcm=gfsk8::modulate(gfsk8::Submode::Normal,frame.frameType,frame.payload,1500.0);
    if (pcm.empty()) throw std::runtime_error("modulation failed");
    // -18 dBFS peak-ish reference, deliberately conservative for initial TX.
    // Real ALC and deviation levels still must be verified on a dummy load.
    constexpr float gain=0.125f;
    std::array<int16_t,1024> block{};
    size_t off=0;
    while (off<pcm.size()) {
        size_t n=std::min(block.size(),pcm.size()-off);
        for(size_t i=0;i<n;++i) {
            float v=std::clamp(pcm[off+i]*gain,-1.0f,1.0f);
            block[i]=static_cast<int16_t>(std::lround(v*32767.0f));
        }
        if (std::fwrite(block.data(),sizeof(int16_t),n,stdout)!=n) return 1;
        off+=n;
    }
    return std::fflush(stdout)==0?0:1;
}
}

int main(int argc,char **argv) {
    if(argc<2) {
        std::cerr<<"Usage: pocketjs8-lite-modem rx | frames --call X --grid Y --message TEXT | tx --call ... --index 0\n";
        return 2;
    }
    try {
        auto cmd=std::string(argv[1]);
        if(cmd=="rx") return receive();
        if(cmd=="frames") return frames(argc,argv);
        if(cmd=="tx") return tx(argc,argv);
        if(cmd=="version") {std::cout<<"PocketJS8 Lite modem bridge 0.3.0 (Normal only)\n";return 0;}
        throw std::runtime_error("unknown command");
    } catch(std::exception const &e) {std::cerr<<"pocketjs8-lite-modem: "<<e.what()<<'\n';return 2;}
}
