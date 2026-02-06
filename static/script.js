let currentId = null;

function mudarTela(tela) {
    document.querySelectorAll('.view-panel').forEach(el => el.style.display = 'none');
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));

    if (tela === 'monitor') {
        document.getElementById('view-monitor').style.display = 'block';
        document.getElementById('nav-monitor').classList.add('active');
        carregarMonitor();
    } else {
        document.getElementById('view-historico').style.display = 'block';
        document.getElementById('nav-historico').classList.add('active');
        carregarHistorico();
    }
}

function fecharModal() {
    document.getElementById('modal-backdrop').classList.remove('active');
}
document.addEventListener('keydown', (e) => { if(e.key === 'Escape') fecharModal(); });
document.getElementById('modal-backdrop').addEventListener('click', (e) => {
    if(e.target.id === 'modal-backdrop') fecharModal();
});

function carregarMonitor() {
    const container = document.getElementById('lista-alertas');
    
    fetch('/api/incidentes')
        .then(res => res.json())
        .then(data => {
            container.innerHTML = '';

            if (!data || data.length === 0) {
                container.innerHTML = `
                    <div style="text-align:center; padding:60px; color:var(--text-muted); background:var(--bg-card); border-radius:12px; border:1px dashed var(--border);">
                        <i class="material-icons-round" style="font-size:48px; margin-bottom:16px; opacity:0.5;">check_circle</i>
                        <p>Nenhum incidente pendente.</p>
                    </div>`;
                return;
            }

            data.forEach(item => {
                const isLos = item.alert_type === 'pon_loss';
                const hora = new Date(item.initial_date).toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit'});
                const tipoClass = isLos ? 'type-los' : 'type-power';
                const badgeClass = isLos ? 'los' : 'power';
                const badgeText = isLos ? 'LOS' : 'ENERGIA';

                const div = document.createElement('div');
                div.className = `incident-card ${tipoClass}`;
                
                div.innerHTML = `
                    <div class="col-badge">
                        <span class="badge ${badgeClass}">${badgeText}</span>
                    </div>
                    
                    <div class="col-time">
                        <i class="material-icons-round" style="font-size:16px; vertical-align:middle; margin-right:4px;">schedule</i>
                        ${hora}
                    </div>

                    <div class="col-meta">
                        <i class="material-icons-round" style="font-size:18px; color:var(--text-muted);">group</i>
                        ${item.total_devices_count} Clientes
                    </div>

                    <div class="col-olt">
                        <i class="material-icons-round">desktop_windows</i>
                        <strong>${item.olt_name}</strong> 
                        <span class="separator">|</span>
                        <span class="slot">${item.slot_pon}</span>
                    </div>

                    <div class="col-actions">
                        <button class="btn-action approve" onclick="acaoRapida(event, ${item.id}, 'aprovar')">Aprovar</button>
                        <button class="btn-action deny" onclick="acaoRapida(event, ${item.id}, 'negar')">Negar</button>
                        <button class="btn-mini-details" onclick="abrirDetalhes(${item.id})" title="Ver Detalhes">
                            <i class="material-icons-round">chevron_right</i>
                        </button>
                    </div>
                `;
                container.appendChild(div);
            });
        })
        .catch(err => {
            container.innerHTML = '<div style="color:var(--danger); text-align:center; padding:20px;">Erro de conexão com API.</div>';
        });
}

function acaoRapida(event, id, acao) {
    event.stopPropagation();
    currentId = id;
    enviarAcao(acao);
}

function abrirDetalhes(id) {
    currentId = id;
    const modal = document.getElementById('modal-backdrop');
    const tbody = document.getElementById('det-tbody');
    const elQtd = document.getElementById('det-qtd');
    const elCausa = document.getElementById('det-causa');
    const iconModal = document.getElementById('modal-icon');
    const subtitle = document.getElementById('modal-subtitle');

    elQtd.innerText = '...';
    elCausa.innerText = 'Carregando...';
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:20px; color:var(--text-muted);">Buscando dados em tempo real...</td></tr>';
    
    modal.classList.add('active');

    fetch(`/api/detalhes/${id}`)
        .then(res => res.json())
        .then(data => {
            const info = data.info;
            elQtd.innerText = info.total_devices_count;
            elCausa.innerText = info.causa_provavel;
            subtitle.innerText = `${info.olt_name} — Slot ${info.slot_pon}`;

            const causaLower = info.causa_provavel.toLowerCase();
            if (causaLower.includes('energia') || causaLower.includes('power')) {
                elCausa.className = 'txt-orange';
                iconModal.innerText = 'bolt';
                iconModal.style.color = 'var(--warning)';
            } else {
                elCausa.className = 'txt-red';
                iconModal.innerText = 'fiber_manual_record';
                iconModal.style.color = 'var(--danger)';
            }

            tbody.innerHTML = '';
            data.clientes.forEach(cli => {
                const tr = document.createElement('tr');
                
                let statusClass = 'txt-green';
                const st = cli.status.toLowerCase();

                if (st.includes('los') || st.includes('fail') || st.includes('offline')) statusClass = 'txt-red';
                else if (st.includes('power') || st.includes('energia')) statusClass = 'txt-orange';

                const contatoDisplay = cli.contact 
                    ? `<span class="txt-green" style="font-family:monospace; letter-spacing:0.5px;">${cli.contact}</span>` 
                    : '<span style="color:#555">-</span>';

                tr.innerHTML = `
                    <td style="font-family:monospace; opacity:0.7;">${cli.sn_onu}</td>
                    <td><strong>${cli.client_name}</strong></td>
                    <td class="${statusClass}">${cli.status}</td>
                    <td>${cli.slot_pon}</td>
                    <td>${contatoDisplay}</td>
                `;
                tbody.appendChild(tr);
            });
        });
}

function enviarAcao(acao) {
    const verbo = acao === 'aprovar' ? 'APROVAR' : 'NEGAR';
    if (!confirm(`Confirma ${verbo} este incidente?`)) return;

    fetch('/api/acao', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: currentId, acao: acao })
    })
    .then(res => res.json())
    .then(data => {
        alert(data.msg);
        if (data.success) {
            fecharModal();
            carregarMonitor();
        }
    });
}


function carregarHistorico() {
    const tbody = document.getElementById('tbody-historico');
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:20px;">Carregando logs...</td></tr>';

    fetch('/api/historico')
        .then(res => res.json())
        .then(data => {
            tbody.innerHTML = '';
            if (!data || data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:20px; color:var(--text-muted);">Histórico vazio.</td></tr>';
                return;
            }
            data.forEach(log => {
                const tr = document.createElement('tr');
                
                const corDecisao = log.acao === 'APROVADO' ? 'txt-green' : 'txt-red';
                
                let statusHtml = '';
                if(log.status_atual === 'ATIVO') {
                    statusHtml = '<span class="badge" style="background:rgba(239,68,68,0.2); color:var(--danger)">AINDA ATIVO</span>';
                } else {
                    statusHtml = '<span class="badge" style="background:rgba(16,185,129,0.2); color:var(--success)">NORMALIZADO</span>';
                }

                let proxEnvioClass = '';
                if(log.liberacao === 'Disponível' || log.liberacao === 'Imediata') {
                    proxEnvioClass = 'txt-green';
                } else {
                    proxEnvioClass = 'txt-orange';
                }

                tr.innerHTML = `
                    <td>${log.data_acao}</td>
                    <td>
                        <strong style="color:#fff">${log.snapshot.olt_name}</strong>
                        <br><span style="font-size:0.8rem; color:var(--text-muted)">${log.snapshot.slot_pon}</span>
                    </td>
                    <td class="${corDecisao}"><strong>${log.acao}</strong></td>
                    
                    <td>${statusHtml}</td>
                    <td class="${proxEnvioClass}" style="font-weight:600; font-family:monospace">
                        ${log.liberacao}
                    </td>
                `;
                tbody.appendChild(tr);
            });
        });
}

carregarMonitor();
setInterval(() => {
    if (document.getElementById('view-monitor').style.display !== 'none') carregarMonitor();
}, 5000);
