//
// This file is a part of UERANSIM project.
// Copyright (c) 2023 ALİ GÜNGÖR.
//
// https://github.com/aligungr/UERANSIM/
// See README, LICENSE, and CONTRIBUTING files for licensing details.
//

#include "task.hpp"
#include <atomic>
#include <cstdint>
#include <cstring>
#include <ue/app/task.hpp>
#include <ue/nas/task.hpp>
#include <ue/nts.hpp>
#include <unistd.h>
#include <utils/libc_error.hpp>
#include <utils/scoped_thread.hpp>

// TODO: May be reduced to MTU 1500
#define RECEIVER_BUFFER_SIZE 8000

struct ReceiverArgs
{
    int fd{};
    int psi{};
    NtsTask *targetTask{};
    NtsTask *backpressureTask{}; // slow downstream task to watch for overload
    std::size_t cap{};           // drop uplink packets when its backlog exceeds this
};

// Uplink user-plane backpressure: the UE's NAS task ciphers every uplink packet
// single-threaded, so a high-rate flood (e.g. a SYN flood from the UE) can enqueue
// faster than it drains, growing the inbox without bound until the UE wedges and
// stops forwarding uplink entirely. Instead, drop the packets that cannot be served.
static std::atomic<uint64_t> g_tunUplinkDropped{0};

static std::string GetErrorMessage(const std::string &cause)
{
    std::string what = cause;

    int errNo = errno;
    if (errNo != 0)
        what += " (" + std::string{strerror(errNo)} + ")";

    return what;
}

static std::unique_ptr<nr::ue::NmUeTunToApp> NmError(std::string &&error)
{
    auto m = std::make_unique<nr::ue::NmUeTunToApp>(nr::ue::NmUeTunToApp::TUN_ERROR);
    m->error = std::move(error);
    return m;
}

static void ReceiverThread(ReceiverArgs *args)
{
    int fd = args->fd;
    int psi = args->psi;
    NtsTask *targetTask = args->targetTask;
    NtsTask *args_backpressureTask = args->backpressureTask;
    std::size_t args_cap = args->cap;

    delete args;

    uint8_t buffer[RECEIVER_BUFFER_SIZE];

    while (true)
    {
        ssize_t n = ::read(fd, buffer, RECEIVER_BUFFER_SIZE);
        if (n < 0)
        {
            targetTask->push(NmError(GetErrorMessage("TUN device could not read")));
            return; // Abort receiver thread
        }

        if (n > 0)
        {
            // Drop uplink packets the (slow, single-threaded) NAS task cannot serve,
            // rather than letting its inbox grow unbounded and wedge the UE.
            if (args_backpressureTask != nullptr && args_cap != 0 &&
                args_backpressureTask->pendingCount() > args_cap)
            {
                g_tunUplinkDropped.fetch_add(1, std::memory_order_relaxed);
                continue;
            }

            auto m = std::make_unique<nr::ue::NmUeTunToApp>(nr::ue::NmUeTunToApp::DATA_PDU_DELIVERY);
            m->psi = psi;
            m->data = OctetString::FromArray(buffer, static_cast<size_t>(n));
            targetTask->push(std::move(m));
        }
    }
}

namespace nr::ue
{

ue::TunTask::TunTask(TaskBase *base, int psi, int fd) : m_base{base}, m_psi{psi}, m_fd{fd}, m_receiver{}
{
}

void TunTask::onStart()
{
    auto *receiverArgs = new ReceiverArgs();
    receiverArgs->fd = m_fd;
    receiverArgs->targetTask = this;
    receiverArgs->psi = m_psi;
    // Watch the NAS task (per-packet uplink ciphering, the single-threaded bottleneck)
    // and drop uplink packets once its backlog grows past the cap.
    receiverArgs->backpressureTask = m_base->nasTask;
    receiverArgs->cap = 4096;
    m_receiver =
        new ScopedThread([](void *args) { ReceiverThread(reinterpret_cast<ReceiverArgs *>(args)); }, receiverArgs);
}

void TunTask::onQuit()
{
    delete m_receiver;
    ::close(m_fd);
}

void TunTask::onLoop()
{
    auto msg = take();
    if (!msg)
        return;

    switch (msg->msgType)
    {
    case NtsMessageType::UE_APP_TO_TUN: {
        auto &w = dynamic_cast<NmAppToTun &>(*msg);
        ssize_t res = ::write(m_fd, w.data.data(), w.data.length());
        if (res < 0)
            push(NmError(GetErrorMessage("TUN device could not write")));
        else if (res != w.data.length())
            push(NmError(GetErrorMessage("TUN device partially written")));
        break;
    }
    case NtsMessageType::UE_TUN_TO_APP: {
        m_base->appTask->push(std::move(msg));
        break;
    }
    default:
        break;
    }
}

} // namespace nr::ue