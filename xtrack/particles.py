import pysixtrack
import numpy as np
import xobjects as xo

from .dress import dress

pmass = 938.2720813e6


scalar_vars = (
    (xo.Int64,   'num_particles'),
    (xo.Float64, 'q0'),
    (xo.Float64, 'mass0'),
    (xo.Float64, 'beta0'),
    (xo.Float64, 'gamma0'),
    (xo.Float64, 'p0c',)
    )

per_particle_vars = [
    (xo.Float64, 's'),
    (xo.Float64, 'x'),
    (xo.Float64, 'y'),
    (xo.Float64, 'px'),
    (xo.Float64, 'py'),
    (xo.Float64, 'zeta'),
    (xo.Float64, 'psigma'),
    (xo.Float64, 'delta'),
    (xo.Float64, 'rpp'),
    (xo.Float64, 'rvv'),
    (xo.Float64, 'chi'),
    (xo.Float64, 'charge_ratio'),
    (xo.Float64, 'weight'),
    (xo.Int64, 'particle_id'),
    (xo.Int64, 'at_element'),
    (xo.Int64, 'at_turn'),
    (xo.Int64, 'state'),
    ]

fields = {}
for tt, nn in scalar_vars:
    fields[nn] = tt

for tt, nn in per_particle_vars:
    fields[nn] = tt[:]

ParticlesData = type(
        'ParticlesData',
        (xo.Struct,),
        fields)

class Particles(dress(ParticlesData)):

    def __init__(self, pysixtrack_particles=None, num_particles=None, **kwargs):


        # Initalize array sizes
        part_dict = pysixtrack_particles_to_xtrack_dict(pysixtrack_particles)
        num_particles = int(part_dict['num_particles'])

        kwargs.update(
                {kk: num_particles for tt, kk in per_particle_vars})
        kwargs['num_particles'] = num_particles

        self.xoinitialize(**kwargs)
        context = self._buffer.context

        for tt, kk in list(scalar_vars):
            setattr(self, kk, part_dict[kk])
        for tt, kk in list(per_particle_vars):
            setattr(self, kk, context.nparray_to_context_array(part_dict[kk]))


    def _set_p0c(self):
        energy0 = np.sqrt(self.p0c ** 2 + self.mass0 ** 2)
        self.beta0 = self.p0c / energy0
        self.gamma0 = energy0 / self.mass0

    def _set_delta(self):
        rep = np.sqrt(self.delta ** 2 + 2 * self.delta + 1 / self.beta0 ** 2)
        irpp = 1 + self.delta
        self.rpp = 1 / irpp
        beta = irpp / rep
        self.rvv = beta / self.beta0
        self.psigma = (
            np.sqrt(self.delta ** 2 + 2 * self.delta + 1 / self.beta0 ** 2)
            / self.beta0
            - 1 / self.beta0 ** 2
        )

    @property
    def ptau(self):
        return (
            np.sqrt(self.delta ** 2 + 2 * self.delta + 1 / self.beta0 ** 2)
            - 1 / self.beta0
        )

    def set_reference(self, p0c=7e12, mass0=pmass, q0=1):
        self.q0 = q0
        self.mass0 = mass0
        self.p0c = p0c
        return self

    def set_particles_from_pysixtrack(self, index, pysixtrack_particle,
            set_scalar_vars=False, check_scalar_vars=True):

        part_dict = pysixtrack_particles_to_xtrack_dict(pysixtrack_particle)
        for tt, kk in list(scalar_vars):
            if kk == 'num_particles':
                continue
            setattr(self, kk, part_dict[kk])
        for tt, kk in list(per_particle_vars):
            getattr(self, kk)[index] = part_dict[kk][0]


def gen_local_particle_api(mode='no_local_copy'):

    if mode != 'no_local_copy':
        raise NotImplementedError

    src_lines = []
    src_lines.append('''typedef struct{''')
    for tt, vv in scalar_vars:
        src_lines.append('                 ' + tt._c_type + '  '+vv+';')
    for tt, vv in per_particle_vars:
        src_lines.append('    /*gpuglmem*/ ' + tt._c_type + '* '+vv+';')
    src_lines.append(    '                 int64_t ipart;')
    src_lines.append('}LocalParticle;')
    src_typedef = '\n'.join(src_lines)

    src_lines = []
    src_lines.append('''
    /*gpufun*/
    void Particles_to_LocalParticle(ParticlesData source,
                                    LocalParticle* dest,
                                    int64_t id){''')
    for tt, vv in scalar_vars:
        src_lines.append(
                f'  dest->{vv} = ParticlesData_get_'+vv+'(source);')
    for tt, vv in per_particle_vars:
        src_lines.append(
                f'  dest->{vv} = ParticlesData_getp1_'+vv+'(source, 0);')
    src_lines.append('  dest->ipart = id;')
    src_lines.append('}')
    src_particles_to_local = '\n'.join(src_lines)

    src_lines=[]
    for tt, vv in per_particle_vars:
        src_lines.append('''
    /*gpufun*/
    void LocalParticle_add_to_'''+vv+f'(LocalParticle* part, {tt._c_type} value)'
    +'{')
        src_lines.append(f'  part->{vv}[part->ipart] += value;')
        src_lines.append('}\n')
    src_adders = '\n'.join(src_lines)

    src_lines=[]
    for tt, vv in per_particle_vars:
        src_lines.append('''
    /*gpufun*/
    void LocalParticle_scale_'''+vv+f'(LocalParticle* part, {tt._c_type} value)'
    +'{')
        src_lines.append(f'  part->{vv}[part->ipart] *= value;')
        src_lines.append('}\n')
    src_scalers = '\n'.join(src_lines)

    src_lines=[]
    for tt, vv in per_particle_vars:
        src_lines.append('''
    /*gpufun*/
    void LocalParticle_set_'''+vv+f'(LocalParticle* part, {tt._c_type} value)'
    +'{')
        src_lines.append(f'  part->{vv}[part->ipart] = value;')
        src_lines.append('}')
    src_setters = '\n'.join(src_lines)

    src_lines=[]
    for tt, vv in scalar_vars:
        src_lines.append('/*gpufun*/')
        src_lines.append(f'{tt._c_type} LocalParticle_get_'+vv
                        + f'(LocalParticle* part)'
                        + '{')
        src_lines.append(f'  return part->{vv};')
        src_lines.append('}')
    for tt, vv in per_particle_vars:
        src_lines.append('/*gpufun*/')
        src_lines.append(f'{tt._c_type} LocalParticle_get_'+vv
                        + f'(LocalParticle* part)'
                        + '{')
        src_lines.append(f'  return part->{vv}[part->ipart];')
        src_lines.append('}')
    src_getters = '\n'.join(src_lines)

    custom_source='''
/*gpufun*/
double LocalParticle_get_energy0(LocalParticle* part){

    double const p0c = LocalParticle_get_p0c(part);
    double const m0  = LocalParticle_get_mass0(part);

    return sqrt( p0c * p0c + m0 * m0 );
}

/*gpufun*/
void LocalParticle_add_to_energy(LocalParticle* part, double delta_energy){

    double const beta0 = LocalParticle_get_beta0(part);
    double const delta_beta0 = LocalParticle_get_delta(part) * beta0;

    double const ptau_beta0 =
        delta_energy / LocalParticle_get_energy0(part) +
        sqrt( delta_beta0 * delta_beta0 + 2.0 * delta_beta0 * beta0
                + 1. ) - 1.;

    double const ptau   = ptau_beta0 / beta0;
    double const psigma = ptau / beta0;
    double const delta = sqrt( ptau * ptau + 2. * psigma + 1 ) - 1;

    double const one_plus_delta = delta + 1.;
    double const rvv = one_plus_delta / ( 1. + ptau_beta0 );

    LocalParticle_set_delta(part, delta );
    LocalParticle_set_psigma(part, psigma );
    LocalParticle_scale_zeta(part,
        rvv / LocalParticle_get_rvv(part));

    LocalParticle_set_rvv(part, rvv );
    LocalParticle_set_rpp(part, 1. / one_plus_delta );
}
'''

    source = '\n\n'.join([src_typedef, src_particles_to_local, src_adders,
                          src_getters, src_setters, src_scalers, custom_source])

    return source

def pysixtrack_particles_to_xtrack_dict(pysixtrack_particles):

    if hasattr(pysixtrack_particles, '__iter__'):
        num_particles = len(pysixtrack_particles)
        dicts = list(map(pysixtrack_particles_to_xtrack_dict, pysixtrack_particles))
        out = {}
        out['num_particles'] = num_particles
        for tt, kk in scalar_vars:
            if kk == 'num_particles':
                continue
            # TODO check consistency
            out[kk] = dicts[0][kk]
        for tt, kk in per_particle_vars:
            out[kk] = np.concatenate([dd[kk] for dd in dicts])
        return out
    else:
        out = {}

        pyst_dict = pysixtrack_particles.to_dict()
        if hasattr(pysixtrack_particles, 'weight'):
            pyst_dict['weight'] = getattr(pysixtrack_particles, 'weight')
        else:
            pyst_dict['weight'] = 1.

        for tt, kk in list(scalar_vars) + list(per_particle_vars):
            if kk not in pyst_dict.keys():
                if kk == 'num_particles':
                    continue
                else:
                    if kk == 'mass_ratio':
                        kk_pyst = 'mratio'
                    elif kk == 'charge_ratio':
                        kk_pyst = 'qratio'
                    elif kk == 'particle_id':
                        kk_pyst = 'partid'
                    elif kk == 'at_element':
                        kk_pyst = 'elemid'
                    elif kk == 'at_turn':
                        kk_pyst = 'turn'
                    else:
                        kk_pyst = kk
                    # Use properties
                    pyst_dict[kk] = getattr(pysixtrack_particles, kk_pyst)

        for kk, vv in pyst_dict.items():
            pyst_dict[kk] = np.atleast_1d(vv)

        lll = [len(vv) for kk, vv in pyst_dict.items() if hasattr(vv, '__len__')]
        lll = list(set(lll))
        assert len(set(lll) - {1}) <= 1
        num_particles = max(lll)
        out['num_particles'] = num_particles

    for tt, kk in scalar_vars:
        if kk == 'num_particles':
            continue
        val = pyst_dict[kk]
        assert np.allclose(val, val[0], rtol=1e-10, atol=1e-14)
        out[kk] = val[0]

    for tt, kk in per_particle_vars:

        val_pyst = pyst_dict[kk]

        if num_particles > 1 and len(val_pyst)==1:
            temp = np.zeros(int(num_particles), dtype=tt._dtype)
            temp += val_pyst[0]
            val_pyst = temp

        if type(val_pyst) != tt._dtype:
            val_pyst = np.array(val_pyst, dtype=tt._dtype)

        out[kk] = val_pyst

    return out
