/*
 *  tsodyks3_synapse.h
 *
 *  This file is part of NEST.
 *
 *  Copyright (C) 2004 The NEST Initiative
 *
 *  NEST is free software: you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation, either version 2 of the License, or
 *  (at your option) any later version.
 *
 *  NEST is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with NEST.  If not, see <http://www.gnu.org/licenses/>.
 *
 */

#ifndef TSODYKS3_SYNAPSE_H
#define TSODYKS3_SYNAPSE_H

// C++ includes:
#include <cmath>

// Includes from nestkernel:
#include "connection.h"

namespace nest
{

/* BeginUserDocs: synapse, short-term plasticity

Short description
+++++++++++++++++

Synapse type with short term plasticity

Description
+++++++++++

This synapse model implements synaptic short-term depression and short-term
facilitation according to [1]_. It solves Eq (5) and Eq (6) from Supporting material of [1]_.

This connection merely scales the synaptic weight, based on the spike history
and the parameters of the kinetic model. Thus, it is suitable for all types
of synaptic dynamics, that is current or conductance based.

The quantity ux in the synapse properties is the
factor that scales the synaptic weight.

.. warning::

   This synaptic plasticity rule does not take
   :doc:`precise spike timing <simulations_with_precise_spike_times>` into
   account. When calculating the weight update, the precise spike time part
   of the timestamp is ignored.

Parameters
++++++++++

The following parameters can be set in the status dictionary:

========  ======  ========================================================
 U        real    Parameter determining the increase in u with each spike
                  (U1) [0,1], default=0.5
 u        real    The probability of release (U_se) [0,1],
                  default=0.5
 x        real    Amount of available resources [0,1], default=1.0
 tau_fac  ms      Time constant for facilitation, default = 0(off)
 tau_rec  ms      Time constant for depression, default = 800ms
========  ======  ========================================================

Remarks:

Under identical conditions, the tsodyks3_synapse produces
slightly higher peak amplitudes than the tsodyks_synapse. However,
the qualitative behavior is identical.

References
++++++++++

.. [1] Mongillo G, Barak O, Tsodyks M (2008). Synaptic Theory of Working
       Memory. Science 319, 1543–1546.
       DOI: https://doi.org/10.1126/science.1150769

Transmits
+++++++++

SpikeEvent

See also
++++++++

tsodyks_synapse, stdp_synapse, static_synapse

EndUserDocs */

template < typename targetidentifierT >
class tsodyks3_synapse : public Connection< targetidentifierT >
{
public:
  typedef CommonSynapseProperties CommonPropertiesType;
  typedef Connection< targetidentifierT > ConnectionBase;
  
  /**
   * The constructor registers the module with the dynamic loader.
   * Initialization proper is performed by the init() method.
   */
  tsodyks3_synapse();

  /**
 * Copy constructor from a property object.
 * Needs to be defined properly in order for GenericConnector to work.
 */
  tsodyks3_synapse( const tsodyks3_synapse& ) = default;

  /**
   * The destructor does not do much in modules.
   */
  ~tsodyks3_synapse()
  {
  }

  // Explicitly declare all methods inherited from the dependent base
  // ConnectionBase. This avoids explicit name prefixes in all places these
  // functions are used. Since ConnectionBase depends on the template parameter,
  // they are not automatically found in the base class.
  using ConnectionBase::get_delay_steps;
  using ConnectionBase::get_delay;
  using ConnectionBase::get_rport;
  using ConnectionBase::get_target;

  /**
   * Get all properties of this connection and put them into a dictionary.
   */
  void get_status( DictionaryDatum& d ) const;

  /**
   * Set properties of this connection from the values given in dictionary.
   */
  void set_status( const DictionaryDatum& d, ConnectorModel& cm );

  /**
   * Send an event to the receiver of this connection.
   * \param e The event to send
   * \param cp Common properties to all synapses (empty).
   */
  void send( Event& e, thread t, const CommonSynapseProperties& cp );


  class ConnTestDummyNode : public ConnTestDummyNodeBase
  {
  public:
    // Ensure proper overriding of overloaded virtual functions.
    // Return values from functions are ignored.
    using ConnTestDummyNodeBase::handles_test_event;
    port
    handles_test_event( SpikeEvent&, rport )
    {
      return invalid_port_;
    }
  };


  void
  check_connection( Node& s, Node& t, rport receptor_type, const CommonPropertiesType& )
  {
    ConnTestDummyNode dummy_target;
    ConnectionBase::check_connection_( dummy_target, s, t, receptor_type );
  }

  void
  set_weight( double w )
  {
    weight_ = w;
  }


private:
  double weight_;
  double U_;           //!< unit increment of a facilitating synapse
  double u_;           //!< dynamic value of probability of release
  double x_;           //!< amount of available resources
  double tau_rec_;     //!< [ms] time constant for recovery
  double tau_fac_;     //!< [ms] time constant for facilitation
  double t_lastspike_; //!< time point of last spike emitted
};


/**
 * Send an event to the receiver of this connection.
 * \param e The event to send
 * \param p The port under which this connection is stored in the Connector.
 */
template < typename targetidentifierT >
inline void
tsodyks3_synapse< targetidentifierT >::send( Event& e, thread t, const CommonSynapseProperties& )
{
  Node* target = get_target( t );
  const double t_spike = e.get_stamp().get_ms();
  const double h = t_spike - t_lastspike_;
  double x_decay = std::exp( -h / tau_rec_ );
  double u_decay = ( tau_fac_ < 1.0e-10 ) ? 0.0 : std::exp( -h / tau_fac_ );

x_ = 1. + (x_ - 1.) * x_decay;
u_ = U_ + (u_ - U_) * u_decay;

u_ += U_ * (1. - u_);

e.set_receiver( *target );
e.set_weight( weight_ * x_ * u_);
// send the spike to the target
e.set_delay_steps( get_delay_steps() );
e.set_rport( get_rport() );
e();


x_ -= u_ * x_;


t_lastspike_ = t_spike;
}

template < typename targetidentifierT >
tsodyks3_synapse< targetidentifierT >::tsodyks3_synapse()
  : ConnectionBase()
  , weight_( 1.0 )
  , U_( 0.5 )
  , u_( U_ )
  , x_( 1.0 )
  , tau_rec_( 800.0 )
  , tau_fac_( 0.0 )
  , t_lastspike_( 0.0 )
{
}

template < typename targetidentifierT >
void
tsodyks3_synapse< targetidentifierT >::get_status( DictionaryDatum& d ) const
{
  ConnectionBase::get_status( d );
  def< double >( d, names::weight, weight_ );

  def< double >( d, names::dU, U_ );
  def< double >( d, names::u, u_ );
  def< double >( d, names::tau_rec, tau_rec_ );
  def< double >( d, names::tau_fac, tau_fac_ );
  def< double >( d, names::x, x_ );
  def< long >( d, names::size_of, sizeof( *this ) );
}

template < typename targetidentifierT >
void
tsodyks3_synapse< targetidentifierT >::set_status( const DictionaryDatum& d, ConnectorModel& cm )
{
  ConnectionBase::set_status( d, cm );
  updateValue< double >( d, names::weight, weight_ );

  updateValue< double >( d, names::dU, U_ );
  if ( U_ > 1.0 || U_ < 0.0 )
  {
    throw BadProperty( "U must be in [0,1]." );
  }

  updateValue< double >( d, names::u, u_ );
  if ( u_ > 1.0 || u_ < 0.0 )
  {
    throw BadProperty( "u must be in [0,1]." );
  }

  updateValue< double >( d, names::tau_rec, tau_rec_ );
  if ( tau_rec_ <= 0.0 )
  {
    throw BadProperty( "tau_rec must be > 0." );
  }

  updateValue< double >( d, names::tau_fac, tau_fac_ );
  if ( tau_fac_ < 0.0 )
  {
    throw BadProperty( "tau_fac must be >= 0." );
  }

  updateValue< double >( d, names::x, x_ );
  if ( x_ > 1.0 || x_ < 0.0 )
  {
    throw BadProperty( "x must be in [0,1]." );
  }
};

} // namespace

#endif // TSODYKS3_SYNAPSE_H
